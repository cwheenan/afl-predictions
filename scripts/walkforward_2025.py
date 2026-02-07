#!/usr/bin/env python3
"""Walk-forward validation for 2025 season.

Simulates real-time prediction by:
1. Training on all data 1990-2024
2. Predicting round 1 of 2025
3. Adding round 1 results to training data and retraining
4. Predicting round 2
5. Repeat for all rounds

This gives a realistic estimate of how models would perform in actual use.

Usage:
  python scripts/walkforward_2025.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("Warning: XGBoost not available")

from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match


def build_feature_matrix(session, matches):
    """Build feature matrix from list of matches."""
    data = []
    for m in matches:
        try:
            fv = features_for_match(session, m.match_id)
        except Exception:
            continue
        if not fv:
            continue
        
        row = dict(fv)
        row['match_id'] = m.match_id
        row['token'] = m.token
        row['season'] = int(m.season) if m.season is not None else None
        row['round'] = m.round
        row['home_team'] = m.home_team
        row['away_team'] = m.away_team
        row['label'] = 1 if (m.home_score > m.away_score) else 0
        data.append(row)
    
    if not data:
        return pd.DataFrame()
    
    return pd.DataFrame(data)


def train_all_models(X_train, y_train):
    """Train all model types and return dict of trained models.
    Uses optimized hyperparameters from tuning."""
    models = {}
    
    # Logistic Regression with scaling (tuned params)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    lr = LogisticRegression(C=0.001, penalty='l2', solver='liblinear', max_iter=2000, random_state=42, verbose=0)
    lr.fit(X_train_scaled, y_train)
    models['logistic'] = {'model': lr, 'scaler': scaler, 'needs_scaling': True}
    
    # Random Forest (tuned params)
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=5, min_samples_split=5, 
        min_samples_leaf=1, max_features='log2', bootstrap=False,
        random_state=42, n_jobs=-1, verbose=0
    )
    rf.fit(X_train, y_train)
    models['random_forest'] = {'model': rf, 'scaler': None, 'needs_scaling': False}
    
    # Gradient Boosting (tuned params)
    gb = GradientBoostingClassifier(
        n_estimators=300, max_depth=3, learning_rate=0.01,
        min_samples_split=2, min_samples_leaf=2, subsample=1.0,
        random_state=42, verbose=0
    )
    gb.fit(X_train, y_train)
    models['gradient_boosting'] = {'model': gb, 'scaler': None, 'needs_scaling': False}
    
    # XGBoost (tuned params)
    if HAS_XGB:
        xgb_clf = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.01,
            subsample=1.0,
            colsample_bytree=0.6,
            min_child_weight=5,
            gamma=0.2,
            random_state=42,
            eval_metric='logloss',
            verbosity=0
        )
        xgb_clf.fit(X_train, y_train)
        models['xgboost'] = {'model': xgb_clf, 'scaler': None, 'needs_scaling': False}
    
    return models


def predict_with_models(models, X):
    """Get predictions from all models."""
    predictions = {}
    for name, model_info in models.items():
        model = model_info['model']
        X_input = X
        
        if model_info['needs_scaling'] and model_info['scaler']:
            X_input = model_info['scaler'].transform(X)
        
        pred = model.predict_proba(X_input)[:, 1]
        predictions[name] = pred
    
    return predictions


def main():
    engine = get_engine()
    session = get_session(engine)
    
    print("=== Walk-Forward Validation for 2025 Season ===\n")
    
    # Get all matches with scores
    all_matches = session.query(Match).filter(
        Match.home_score != None,
        Match.away_score != None
    ).order_by(Match.season, Match.match_id).all()
    
    print(f"Total matches in database: {len(all_matches)}")
    
    # Split into pre-2025 and 2025
    pre_2025_matches = [m for m in all_matches if m.season and int(m.season) < 2025]
    matches_2025 = [m for m in all_matches if m.season and int(m.season) == 2025]
    
    print(f"Training data (1990-2024): {len(pre_2025_matches)} matches")
    print(f"Test data (2025): {len(matches_2025)} matches")
    
    if not matches_2025:
        print("\nNo matches found for 2025 season")
        return
    
    # Group 2025 matches by round
    rounds_2025 = {}
    for m in matches_2025:
        r = m.round
        if r not in rounds_2025:
            rounds_2025[r] = []
        rounds_2025[r].append(m)
    
    # Sort rounds
    sorted_rounds = sorted(rounds_2025.keys(), key=lambda x: (
        0 if x and 'Grand Final' in x else 
        1 if x and 'Preliminary' in x else
        2 if x and 'Semi' in x else
        3 if x and 'Elimination' in x else
        4 if x and 'Qualifying' in x else
        int(x) if x and x.isdigit() else 999
    ))
    
    print(f"\nRounds in 2025: {sorted_rounds}\n")
    
    # Build initial training data
    print("Building initial training dataset (1990-2024)...")
    train_df = build_feature_matrix(session, pre_2025_matches)
    
    if train_df.empty:
        print("Failed to build training dataset")
        return
    
    meta_cols = {'match_id', 'token', 'season', 'round', 'home_team', 'away_team', 'label'}
    feature_cols = [c for c in train_df.columns if c not in meta_cols]
    
    print(f"Initial training: {len(train_df)} matches, {len(feature_cols)} features\n")
    
    # Track predictions and results
    all_predictions = []
    round_results = []
    
    # Current training data
    current_train_df = train_df.copy()
    
    # Walk forward through each round
    for round_num in sorted_rounds:
        round_matches = rounds_2025[round_num]
        print(f"=== Round: {round_num} ({len(round_matches)} matches) ===")
        
        # Train models on current data
        print("  Training models...", end='', flush=True)
        X_train = current_train_df[feature_cols].fillna(0).values
        y_train = current_train_df['label'].values
        models = train_all_models(X_train, y_train)
        print(" ✓")
        
        # Build features for this round
        print("  Extracting features...", end='', flush=True)
        round_df = build_feature_matrix(session, round_matches)
        if round_df.empty:
            print(" (no features available, skipping)")
            continue
        print(" ✓")
        
        # Make predictions
        print("  Making predictions...", end='', flush=True)
        X_test = round_df[feature_cols].fillna(0).values
        y_test = round_df['label'].values
        
        model_preds = predict_with_models(models, X_test)
        print(" ✓")
        
        # Record predictions and evaluate
        print("  Evaluating models:")
        round_acc = {'round': round_num, 'n_matches': len(round_matches)}
        
        for model_name, preds in model_preds.items():
            acc = accuracy_score(y_test, (preds >= 0.5).astype(int))
            auc = roc_auc_score(y_test, preds) if len(np.unique(y_test)) > 1 else 0.5
            brier = brier_score_loss(y_test, preds)
            
            print(f"    {model_name:20s}: Acc={acc:.3f}, AUC={auc:.3f}, Brier={brier:.3f}")
            
            round_acc[f'{model_name}_acc'] = acc
            round_acc[f'{model_name}_auc'] = auc
            round_acc[f'{model_name}_brier'] = brier
            
            # Store individual predictions
            for i, (idx, row) in enumerate(round_df.iterrows()):
                all_predictions.append({
                    'round': round_num,
                    'match_id': row['match_id'],
                    'home_team': row['home_team'],
                    'away_team': row['away_team'],
                    'model': model_name,
                    'prediction_prob': preds[i],
                    'prediction': 1 if preds[i] >= 0.5 else 0,
                    'actual': y_test[i],
                    'correct': (preds[i] >= 0.5) == y_test[i]
                })
        
        round_results.append(round_acc)
        
        # Calculate ensemble predictions
        ensemble_pred = np.mean([preds for preds in model_preds.values()], axis=0)
        ensemble_acc = accuracy_score(y_test, (ensemble_pred >= 0.5).astype(int))
        ensemble_auc = roc_auc_score(y_test, ensemble_pred) if len(np.unique(y_test)) > 1 else 0.5
        print(f"    {'Ensemble':20s}: Acc={ensemble_acc:.3f}, AUC={ensemble_auc:.3f}")
        
        # Add this round to training data for next round
        print(f"  Adding {len(round_df)} matches to training data")
        current_train_df = pd.concat([current_train_df, round_df], ignore_index=True)
        print()
    
    # Summary statistics
    print("\n=== SUMMARY STATISTICS ===\n")
    
    results_df = pd.DataFrame(round_results)
    
    # Overall accuracy by model
    pred_df = pd.DataFrame(all_predictions)
    
    print("Overall Accuracy by Model:")
    for model_name in pred_df['model'].unique():
        model_preds = pred_df[pred_df['model'] == model_name]
        overall_acc = model_preds['correct'].mean()
        print(f"  {model_name:20s}: {overall_acc:.4f} ({model_preds['correct'].sum()}/{len(model_preds)} correct)")
    
    # Ensemble
    ensemble_preds = pred_df.pivot_table(
        index=['match_id', 'actual'], 
        columns='model', 
        values='prediction_prob'
    ).reset_index()
    model_cols = [c for c in ensemble_preds.columns if c not in ['match_id', 'actual']]
    ensemble_preds['ensemble_prob'] = ensemble_preds[model_cols].mean(axis=1)
    ensemble_preds['ensemble_pred'] = (ensemble_preds['ensemble_prob'] >= 0.5).astype(int)
    ensemble_preds['correct'] = (ensemble_preds['ensemble_pred'] == ensemble_preds['actual'])
    ensemble_acc = ensemble_preds['correct'].mean()
    print(f"  {'Ensemble (equal)':20s}: {ensemble_acc:.4f} ({ensemble_preds['correct'].sum()}/{len(ensemble_preds)} correct)")
    
    # Save results
    output_dir = Path('models')
    output_dir.mkdir(exist_ok=True)
    
    pred_df.to_csv(output_dir / 'walkforward_2025_predictions.csv', index=False)
    results_df.to_csv(output_dir / 'walkforward_2025_by_round.csv', index=False)
    
    print(f"\nResults saved to:")
    print(f"  - {output_dir / 'walkforward_2025_predictions.csv'}")
    print(f"  - {output_dir / 'walkforward_2025_by_round.csv'}")
    
    # Show accuracy by round
    print("\n=== Accuracy by Round ===")
    print(results_df[['round', 'n_matches'] + [c for c in results_df.columns if c.endswith('_acc')]].to_string(index=False))


if __name__ == '__main__':
    main()
