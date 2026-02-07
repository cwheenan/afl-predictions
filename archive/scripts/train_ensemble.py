#!/usr/bin/env python3
"""Train ensemble of multiple models with dynamic weighting.

This script trains multiple model types (XGBoost, Random Forest, Logistic Regression,
Gradient Boosting) and creates an ensemble with performance tracking capabilities.

The ensemble can dynamically adjust model weights based on recent performance during
the season, allowing better models to be weighted more heavily.

Usage:
  python scripts/train_ensemble.py --train --save
  python scripts/train_ensemble.py --evaluate --season 2024
  python scripts/train_ensemble.py --predict --token <token>
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss, log_loss
from joblib import dump, load

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("Warning: XGBoost not available")

from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match


class EnsembleTracker:
    """Track predictions and performance for each model in the ensemble."""
    
    def __init__(self, models_dir='models'):
        self.models_dir = Path(models_dir)
        self.performance_file = self.models_dir / 'ensemble_performance.json'
        self.predictions_file = self.models_dir / 'ensemble_predictions.csv'
        self.weights_file = self.models_dir / 'ensemble_weights.json'
        
        # Initialize or load performance history
        self.performance = self._load_performance()
        
    def _load_performance(self):
        """Load performance history from disk."""
        if self.performance_file.exists():
            with open(self.performance_file, 'r') as f:
                return json.load(f)
        return {
            'by_model': {},
            'by_season': {},
            'rolling_window': 10,  # Number of recent matches to consider
        }
    
    def save_performance(self):
        """Save performance history to disk."""
        self.models_dir.mkdir(exist_ok=True)
        with open(self.performance_file, 'w') as f:
            json.dump(self.performance, f, indent=2)
    
    def record_prediction(self, model_name, match_id, token, season, prob, actual=None):
        """Record a prediction from a specific model."""
        prediction = {
            'timestamp': datetime.now().isoformat(),
            'model': model_name,
            'match_id': match_id,
            'token': token,
            'season': season,
            'probability': float(prob),
            'actual': int(actual) if actual is not None else None,
        }
        
        # Append to predictions file
        df = pd.DataFrame([prediction])
        if self.predictions_file.exists():
            df.to_csv(self.predictions_file, mode='a', header=False, index=False)
        else:
            df.to_csv(self.predictions_file, index=False)
    
    def update_performance(self, model_name, predictions, actuals, season=None):
        """Update performance metrics for a model."""
        try:
            acc = accuracy_score(actuals, (predictions >= 0.5).astype(int))
            auc = roc_auc_score(actuals, predictions) if len(np.unique(actuals)) > 1 else 0.5
            brier = brier_score_loss(actuals, predictions)
            logloss = log_loss(actuals, predictions)
            
            if model_name not in self.performance['by_model']:
                self.performance['by_model'][model_name] = []
            
            self.performance['by_model'][model_name].append({
                'timestamp': datetime.now().isoformat(),
                'season': int(season) if season is not None else None,
                'accuracy': float(acc),
                'auc': float(auc),
                'brier': float(brier),
                'log_loss': float(logloss),
                'n_samples': int(len(actuals)),
            })
            
            self.save_performance()
        except Exception as e:
            print(f"Warning: Failed to update performance for {model_name}: {e}")
    
    def get_dynamic_weights(self, window=None):
        """Calculate dynamic weights based on recent performance.
        
        Uses recent accuracy to weight models. Better performing models get higher weight.
        """
        if window is None:
            window = self.performance.get('rolling_window', 10)
        
        weights = {}
        for model_name, history in self.performance['by_model'].items():
            if not history:
                weights[model_name] = 1.0
                continue
            
            # Get recent performance (last 'window' evaluations)
            recent = history[-window:]
            
            # Weight by accuracy (could use other metrics)
            avg_acc = np.mean([h['accuracy'] for h in recent])
            weights[model_name] = avg_acc
        
        # Normalize weights to sum to 1
        total = sum(weights.values())
        if total > 0:
            weights = {k: v/total for k, v in weights.items()}
        else:
            # Equal weights if no history
            n = len(weights)
            weights = {k: 1.0/n for k in weights.keys()}
        
        return weights
    
    def save_weights(self, weights):
        """Save current weights to disk."""
        with open(self.weights_file, 'w') as f:
            json.dump(weights, f, indent=2)


def build_dataset(session):
    """Build feature matrix X and labels y from processed DB."""
    rows = session.query(Match).filter(
        Match.home_score != None,
        Match.away_score != None
    ).all()
    
    data = []
    errors = 0
    for i, m in enumerate(rows):
        if i % 500 == 0:
            print(f"Processing match {i}/{len(rows)}...")
        try:
            fv = features_for_match(session, m.match_id)
        except Exception as e:
            errors += 1
            if errors < 5:
                print(f"Warning: Failed to extract features for match {m.match_id}: {e}")
            continue
        if not fv:
            continue
        
        row = dict(fv)
        row['match_id'] = m.match_id
        row['token'] = m.token
        row['season'] = int(m.season) if m.season is not None else None
        row['label'] = 1 if (m.home_score > m.away_score) else 0
        data.append(row)
    
    if errors > 0:
        print(f"Total feature extraction errors: {errors}/{len(rows)}")
    
    if not data:
        return pd.DataFrame()
    
    df = pd.DataFrame(data)
    df = df.dropna(subset=['season'])
    df['season'] = df['season'].astype(int)
    return df


def train_models(X_train, y_train, models_dir):
    """Train all model types in the ensemble."""
    models = {}
    
    # Scale features for models that need it
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    
    print("Training Logistic Regression...")
    lr = LogisticRegression(max_iter=2000, random_state=42)
    lr.fit(X_train_scaled, y_train)
    models['logistic'] = {'model': lr, 'scaler': scaler, 'needs_scaling': True}
    
    print("Training Random Forest...")
    rf = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    models['random_forest'] = {'model': rf, 'scaler': None, 'needs_scaling': False}
    
    print("Training Gradient Boosting...")
    gb = GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)
    gb.fit(X_train, y_train)
    models['gradient_boosting'] = {'model': gb, 'scaler': None, 'needs_scaling': False}
    
    if HAS_XGB:
        print("Training XGBoost...")
        xgb_clf = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            eval_metric='logloss'
        )
        xgb_clf.fit(X_train, y_train)
        models['xgboost'] = {'model': xgb_clf, 'scaler': None, 'needs_scaling': False}
    
    return models


def predict_ensemble(models, X, weights=None):
    """Make ensemble predictions using weighted averaging."""
    if weights is None:
        # Equal weights
        weights = {name: 1.0/len(models) for name in models.keys()}
    
    predictions = []
    for name, model_info in models.items():
        model = model_info['model']
        X_input = X
        
        if model_info['needs_scaling'] and model_info['scaler']:
            X_input = model_info['scaler'].transform(X)
        
        pred = model.predict_proba(X_input)[:, 1]
        weighted_pred = pred * weights.get(name, 1.0/len(models))
        predictions.append(weighted_pred)
    
    # Sum weighted predictions
    ensemble_pred = np.sum(predictions, axis=0)
    return ensemble_pred


def temporal_cv_ensemble(df, feature_cols, models_dir):
    """Perform temporal CV with ensemble tracking."""
    seasons = sorted(df['season'].unique())
    tracker = EnsembleTracker(models_dir)
    
    results = []
    
    for s in seasons:
        train_df = df[df['season'] < s]
        test_df = df[df['season'] == s]
        
        if train_df.empty or test_df.empty or len(train_df) < 100:
            continue
        
        print(f"\n=== Season {s} ===")
        print(f"Train: {len(train_df)} matches, Test: {len(test_df)} matches")
        
        X_train = train_df[feature_cols].fillna(0).values
        y_train = train_df['label'].values
        X_test = test_df[feature_cols].fillna(0).values
        y_test = test_df['label'].values
        
        # Train all models
        models = train_models(X_train, y_train, models_dir)
        
        # Evaluate each model individually
        model_preds = {}
        for name, model_info in models.items():
            model = model_info['model']
            X_input = X_test
            
            if model_info['needs_scaling'] and model_info['scaler']:
                X_input = model_info['scaler'].transform(X_test)
            
            pred = model.predict_proba(X_input)[:, 1]
            model_preds[name] = pred
            
            # Calculate metrics
            acc = accuracy_score(y_test, (pred >= 0.5).astype(int))
            auc = roc_auc_score(y_test, pred) if len(np.unique(y_test)) > 1 else 0.5
            brier = brier_score_loss(y_test, pred)
            
            print(f"{name:20s} - Acc: {acc:.4f}, AUC: {auc:.4f}, Brier: {brier:.4f}")
            
            # Update tracker
            tracker.update_performance(name, pred, y_test, season=s)
        
        # Ensemble with equal weights
        weights_equal = {name: 1.0/len(models) for name in models.keys()}
        ensemble_pred_equal = predict_ensemble(models, X_test, weights_equal)
        acc_ens_eq = accuracy_score(y_test, (ensemble_pred_equal >= 0.5).astype(int))
        auc_ens_eq = roc_auc_score(y_test, ensemble_pred_equal) if len(np.unique(y_test)) > 1 else 0.5
        brier_ens_eq = brier_score_loss(y_test, ensemble_pred_equal)
        
        print(f"{'Ensemble (equal)':20s} - Acc: {acc_ens_eq:.4f}, AUC: {auc_ens_eq:.4f}, Brier: {brier_ens_eq:.4f}")
        
        # Ensemble with dynamic weights (if we have history)
        weights_dynamic = tracker.get_dynamic_weights()
        ensemble_pred_dyn = predict_ensemble(models, X_test, weights_dynamic)
        acc_ens_dyn = accuracy_score(y_test, (ensemble_pred_dyn >= 0.5).astype(int))
        auc_ens_dyn = roc_auc_score(y_test, ensemble_pred_dyn) if len(np.unique(y_test)) > 1 else 0.5
        brier_ens_dyn = brier_score_loss(y_test, ensemble_pred_dyn)
        
        print(f"{'Ensemble (dynamic)':20s} - Acc: {acc_ens_dyn:.4f}, AUC: {auc_ens_dyn:.4f}, Brier: {brier_ens_dyn:.4f}")
        print(f"Dynamic weights: {json.dumps({k: round(v, 3) for k, v in weights_dynamic.items()})}")
        
        results.append({
            'season': s,
            'n_train': len(train_df),
            'n_test': len(test_df),
            **{f'{name}_acc': accuracy_score(y_test, (model_preds[name] >= 0.5).astype(int))
               for name in model_preds.keys()},
            **{f'{name}_auc': roc_auc_score(y_test, model_preds[name]) if len(np.unique(y_test)) > 1 else 0.5
               for name in model_preds.keys()},
            'ensemble_equal_acc': acc_ens_eq,
            'ensemble_equal_auc': auc_ens_eq,
            'ensemble_dynamic_acc': acc_ens_dyn,
            'ensemble_dynamic_auc': auc_ens_dyn,
        })
    
    return pd.DataFrame(results), tracker


def train_and_save_final(df, feature_cols, models_dir):
    """Train final models on all data and save."""
    print("\nTraining final ensemble on all data...")
    
    X = df[feature_cols].fillna(0).values
    y = df['label'].values
    
    models = train_models(X, y, models_dir)
    
    # Save all models
    models_path = Path(models_dir)
    models_path.mkdir(exist_ok=True)
    
    for name, model_info in models.items():
        model_file = models_path / f'{name}_final.joblib'
        dump(model_info, model_file)
        print(f"Saved {name} to {model_file}")
    
    # Save feature names
    with open(models_path / 'feature_names.json', 'w') as f:
        json.dump(feature_cols, f, indent=2)
    
    # Initialize tracker with equal weights
    tracker = EnsembleTracker(models_dir)
    weights = {name: 1.0/len(models) for name in models.keys()}
    tracker.save_weights(weights)
    
    print(f"\nSaved {len(models)} models to {models_dir}")


def main():
    parser = argparse.ArgumentParser(description='Train ensemble of AFL prediction models')
    parser.add_argument('--train', action='store_true', help='Train models with temporal CV')
    parser.add_argument('--save', action='store_true', help='Save final models')
    parser.add_argument('--evaluate', action='store_true', help='Evaluate on specific season')
    parser.add_argument('--predict', action='store_true', help='Make prediction for a match')
    parser.add_argument('--season', type=int, help='Season to evaluate')
    parser.add_argument('--token', type=str, help='Match token to predict')
    parser.add_argument('--models-dir', default='models', help='Directory to save/load models')
    
    args = parser.parse_args()
    
    engine = get_engine()
    session = get_session(engine)
    
    # Build dataset
    print("Building dataset from database...")
    df = build_dataset(session)
    
    if df.empty:
        print("No labeled matches available in DB")
        return
    
    # Get feature columns
    meta_cols = {'match_id', 'token', 'season', 'label'}
    feature_cols = [c for c in df.columns if c not in meta_cols]
    
    print(f"Dataset: {len(df)} matches, {len(feature_cols)} features")
    print(f"Seasons: {df['season'].min()}-{df['season'].max()}")
    
    if args.train:
        print("\n=== Training Ensemble with Temporal CV ===")
        results, tracker = temporal_cv_ensemble(df, feature_cols, args.models_dir)
        
        if not results.empty:
            print("\n=== Summary Statistics ===")
            print(results[['season', 'n_train', 'n_test', 
                          'ensemble_equal_acc', 'ensemble_dynamic_acc']].to_string(index=False))
            
            # Save results
            results_file = Path(args.models_dir) / 'ensemble_cv_results.csv'
            results.to_csv(results_file, index=False)
            print(f"\nSaved CV results to {results_file}")
    
    if args.save:
        train_and_save_final(df, feature_cols, args.models_dir)
    
    if args.predict and args.token:
        print(f"\n=== Predicting for token: {args.token} ===")
        # Load models
        models_path = Path(args.models_dir)
        tracker = EnsembleTracker(args.models_dir)
        
        # Load all models
        models = {}
        for model_file in models_path.glob('*_final.joblib'):
            name = model_file.stem.replace('_final', '')
            models[name] = load(model_file)
        
        # Load feature names
        with open(models_path / 'feature_names.json', 'r') as f:
            feature_cols = json.load(f)
        
        # Get match
        match = session.query(Match).filter_by(token=args.token).first()
        if not match:
            print(f"Match not found for token {args.token}")
            return
        
        # Build features
        fv = features_for_match(session, match.match_id)
        if not fv:
            print("No features available for this match")
            return
        X = np.array([fv.get(c, 0.0) for c in feature_cols]).reshape(1, -1)
        
        # Predict with each model
        print("\nIndividual model predictions:")
        for name, model_info in models.items():
            model = model_info['model']
            X_input = X
            if model_info['needs_scaling'] and model_info['scaler']:
                X_input = model_info['scaler'].transform(X)
            
            prob = model.predict_proba(X_input)[0, 1]
            print(f"  {name:20s}: P(home_win) = {prob:.4f}")
        
        # Ensemble prediction
        weights = tracker.get_dynamic_weights()
        ensemble_prob = predict_ensemble(models, X, weights)[0]
        
        print(f"\nEnsemble prediction (dynamic weights):")
        print(f"  P(home_win) = {ensemble_prob:.4f}")
        print(f"  Weights: {json.dumps({k: round(v, 3) for k, v in weights.items()})}")


if __name__ == '__main__':
    main()
