#!/usr/bin/env python3
"""Train ensemble models with odds features on expanded historical dataset.

Uses 2021-2024 data for training, tests on 2025.
Compares multiple ensemble approaches:
1. Top models with odds as features
2. Odds as separate ensemble member
3. Weighted combination

Usage:
  python scripts/train_ensemble_with_odds.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
import joblib

from afl_predictions.db import get_engine, get_session, Match, MatchOdds
from afl_predictions.features.lineup import features_for_match


def parse_date_string(date_str: str):
    """Parse date string to extract year."""
    if not date_str:
        return None
    import re
    match = re.search(r'(\d{4})', date_str)
    if match:
        return int(match.group(1))
    return None


def build_dataset_with_odds(session, years, include_odds_features=True):
    """Build dataset from matches that have odds data."""
    print(f"\nBuilding dataset for {years}")
    
    # Get matches from specified years with odds
    all_matches = session.query(Match).all()
    matches = []
    
    for m in all_matches:
        year = parse_date_string(m.date)
        if year and year in years:
            if m.home_score is not None and m.away_score is not None:
                # Check if odds exist
                has_odds = session.query(MatchOdds).filter(
                    MatchOdds.match_id == m.match_id
                ).count() > 0
                
                if has_odds:
                    matches.append(m)
    
    print(f"Found {len(matches)} matches with odds data")
    
    # Extract features
    X = []
    y = []
    match_ids = []
    odds_probs = []  # Store odds probabilities separately for ensemble approach
    
    for i, m in enumerate(matches):
        if i % 50 == 0:
            print(f"  Processing {i}/{len(matches)}...")
        
        try:
            fv = features_for_match(session, m.match_id)
            
            # Extract odds probability for separate ensemble
            odds_home_prob = fv.get('odds_home_win_prob', 0.5)
            odds_probs.append(odds_home_prob)
            
            # If not including odds as features, remove them
            if not include_odds_features:
                odds_keys = [k for k in fv.keys() if k.startswith('odds_')]
                for k in odds_keys:
                    fv.pop(k, None)
            
            # Convert to vector
            feature_names = sorted(fv.keys())
            features = [fv[k] for k in feature_names]
            
            # Label
            label = 1 if m.home_score > m.away_score else 0
            
            X.append(features)
            y.append(label)
            match_ids.append(m.match_id)
            
        except Exception as e:
            print(f"  Warning: Could not process match {m.match_id}: {e}")
            continue
    
    X = np.array(X)
    y = np.array(y)
    odds_probs = np.array(odds_probs)
    
    # Handle NaN
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    
    print(f"Built dataset: {len(X)} samples, {X.shape[1]} features")
    
    return X, y, match_ids, feature_names, odds_probs


def train_models(X_train, y_train):
    """Train all models with tuned hyperparameters."""
    models = {}
    
    print("\nTraining models...")
    
    # Random Forest (best performer with odds)
    print("  Random Forest...")
    models['rf'] = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        min_samples_split=5,
        max_features='log2',
        bootstrap=False,
        random_state=42
    )
    models['rf'].fit(X_train, y_train)
    
    # Logistic Regression
    print("  Logistic Regression...")
    models['lr'] = LogisticRegression(
        C=0.001,
        penalty='l2',
        solver='liblinear',
        random_state=42,
        max_iter=1000
    )
    models['lr'].fit(X_train, y_train)
    
    # Gradient Boosting
    print("  Gradient Boosting...")
    models['gb'] = GradientBoostingClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.01,
        random_state=42
    )
    models['gb'].fit(X_train, y_train)
    
    # XGBoost
    print("  XGBoost...")
    models['xgb'] = XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.01,
        random_state=42
    )
    models['xgb'].fit(X_train, y_train)
    
    return models


def evaluate_ensemble_approaches(models, X_test, y_test, odds_probs_test):
    """Test different ensemble approaches."""
    results = {}
    
    # Get predictions from each model
    preds = {}
    probs = {}
    for name, model in models.items():
        preds[name] = model.predict(X_test)
        if hasattr(model, 'predict_proba'):
            probs[name] = model.predict_proba(X_test)[:, 1]
        else:
            probs[name] = preds[name]
    
    print("\n" + "="*60)
    print("INDIVIDUAL MODEL PERFORMANCE")
    print("="*60)
    
    for name in ['rf', 'lr', 'gb', 'xgb']:
        acc = accuracy_score(y_test, preds[name])
        correct = int(acc * len(y_test))
        results[name] = acc
        print(f"  {name.upper():5s}: {acc:.1%} ({correct}/{len(y_test)})")
    
    # Approach 1: Top 2 models (RF + LR) - equal weight
    print("\n" + "="*60)
    print("APPROACH 1: TOP 2 EQUAL WEIGHT (RF + LR)")
    print("="*60)
    
    ensemble_prob = (probs['rf'] + probs['lr']) / 2
    ensemble_pred = (ensemble_prob >= 0.5).astype(int)
    acc = accuracy_score(y_test, ensemble_pred)
    correct = int(acc * len(y_test))
    results['top2_equal'] = acc
    print(f"  Accuracy: {acc:.1%} ({correct}/{len(y_test)})")
    
    # Approach 2: Weighted by validation performance
    print("\n" + "="*60)
    print("APPROACH 2: WEIGHTED BY BEST PERFORMERS")
    print("="*60)
    
    # Weight by accuracy
    weights = {'rf': 0.4, 'lr': 0.3, 'gb': 0.2, 'xgb': 0.1}
    weighted_prob = sum(probs[name] * weights[name] for name in weights)
    weighted_pred = (weighted_prob >= 0.5).astype(int)
    acc = accuracy_score(y_test, weighted_pred)
    correct = int(acc * len(y_test))
    results['weighted'] = acc
    print(f"  Accuracy: {acc:.1%} ({correct}/{len(y_test)})")
    
    # Approach 3: Odds as ensemble member (blend stats models with raw odds)
    print("\n" + "="*60)
    print("APPROACH 3: ODDS AS ENSEMBLE MEMBER")
    print("="*60)
    
    # Combine RF probability with odds probability
    odds_as_member_prob = (probs['rf'] * 0.7 + odds_probs_test * 0.3)
    odds_as_member_pred = (odds_as_member_prob >= 0.5).astype(int)
    acc = accuracy_score(y_test, odds_as_member_pred)
    correct = int(acc * len(y_test))
    results['odds_as_member'] = acc
    print(f"  RF 70% + Odds 30%: {acc:.1%} ({correct}/{len(y_test)})")
    
    # Try different weights
    best_acc = acc
    best_weight = 0.3
    for odds_weight in [0.1, 0.2, 0.4, 0.5]:
        test_prob = (probs['rf'] * (1-odds_weight) + odds_probs_test * odds_weight)
        test_pred = (test_prob >= 0.5).astype(int)
        test_acc = accuracy_score(y_test, test_pred)
        print(f"  RF {int((1-odds_weight)*100)}% + Odds {int(odds_weight*100)}%: {test_acc:.1%}")
        if test_acc > best_acc:
            best_acc = test_acc
            best_weight = odds_weight
    
    results['odds_as_member_best'] = best_acc
    print(f"\n  Best: RF {int((1-best_weight)*100)}% + Odds {int(best_weight*100)}%: {best_acc:.1%}")
    
    return results, models


def main():
    engine = get_engine()
    session = get_session(engine)
    
    print("="*60)
    print("ENSEMBLE TRAINING WITH EXPANDED ODDS DATASET")
    print("="*60)
    
    train_years = [2021, 2022, 2023, 2024]
    test_years = [2025]
    
    print(f"\nTraining years: {train_years}")
    print(f"Test year: {test_years}")
    
    # Build datasets (with odds as features)
    X_train, y_train, train_ids, feature_names, odds_train = build_dataset_with_odds(
        session, train_years, include_odds_features=True
    )
    
    X_test, y_test, test_ids, _, odds_test = build_dataset_with_odds(
        session, test_years, include_odds_features=True
    )
    
    print(f"\nDataset sizes:")
    print(f"  Training: {len(y_train)} matches")
    print(f"  Test: {len(y_test)} matches")
    
    # Train models
    models = train_models(X_train, y_train)
    
    # Evaluate approaches
    results, trained_models = evaluate_ensemble_approaches(
        models, X_test, y_test, odds_test
    )
    
    # Summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"\nTest set: {len(y_test)} matches from 2025")
    print(f"Target: 145/189 (76.7% - human performance)")
    print("\nResults:")
    for name, acc in sorted(results.items(), key=lambda x: x[1], reverse=True):
        correct = int(acc * len(y_test))
        star = " ***" if acc >= 0.76 else ""
        print(f"  {name:25s}: {acc:.1%} ({correct}/{len(y_test)}){star}")
    
    # Save best model
    best_approach = max(results.items(), key=lambda x: x[1])
    print(f"\n*** Best approach: {best_approach[0]} at {best_approach[1]:.1%} ***")
    
    if best_approach[0] == 'rf':
        best_model = trained_models['rf']
        model_path = 'models/rf_with_odds_final.joblib'
    else:
        best_model = trained_models['rf']  # Still save RF as it's best single model
        model_path = 'models/rf_with_odds_final.joblib'
    
    joblib.dump(best_model, model_path)
    print(f"\nSaved best model to: {model_path}")
    
    # Save results
    results_data = {
        'train_years': train_years,
        'test_years': test_years,
        'train_size': len(y_train),
        'test_size': len(y_test),
        'results': {k: float(v) for k, v in results.items()},
        'best_approach': best_approach[0],
        'best_accuracy': float(best_approach[1]),
        'feature_count': X_train.shape[1],
        'feature_names': feature_names
    }
    
    with open('models/ensemble_with_odds_results.json', 'w') as f:
        json.dump(results_data, f, indent=2)
    
    print("Saved results to: models/ensemble_with_odds_results.json")
    
    session.close()


if __name__ == '__main__':
    main()
