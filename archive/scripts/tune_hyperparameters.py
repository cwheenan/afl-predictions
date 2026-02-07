#!/usr/bin/env python3
"""Hyperparameter tuning for AFL prediction models.

Uses GridSearchCV and RandomizedSearchCV to find optimal parameters.
Tests on 2025 walk-forward validation to measure real-world performance.

Usage:
  python scripts/tune_hyperparameters.py --model random_forest
  python scripts/tune_hyperparameters.py --model logistic
  python scripts/tune_hyperparameters.py --model xgboost
  python scripts/tune_hyperparameters.py --model all
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV
from sklearn.metrics import accuracy_score, roc_auc_score, make_scorer

try:
    import xgboost as xgb
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

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
        row['label'] = 1 if (m.home_score > m.away_score) else 0
        data.append(row)
    
    return pd.DataFrame(data) if data else pd.DataFrame()


def tune_logistic_regression(X_train, y_train, X_test, y_test):
    """Tune Logistic Regression hyperparameters."""
    print("\n=== Tuning Logistic Regression ===")
    
    # Scale data
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    param_grid = {
        'C': [0.001, 0.01, 0.1, 1, 10, 100],
        'penalty': ['l1', 'l2'],
        'solver': ['liblinear', 'saga'],
        'max_iter': [2000]
    }
    
    lr = LogisticRegression(random_state=42)
    grid = GridSearchCV(lr, param_grid, cv=5, scoring='accuracy', n_jobs=-1, verbose=1)
    
    print("Running grid search...")
    grid.fit(X_train_scaled, y_train)
    
    print(f"\nBest parameters: {grid.best_params_}")
    print(f"Best CV score: {grid.best_score_:.4f}")
    
    # Test on held-out data
    y_pred = grid.best_estimator_.predict(X_test_scaled)
    test_acc = accuracy_score(y_test, y_pred)
    test_auc = roc_auc_score(y_test, grid.best_estimator_.predict_proba(X_test_scaled)[:, 1])
    
    print(f"Test accuracy: {test_acc:.4f}")
    print(f"Test AUC: {test_auc:.4f}")
    
    return grid.best_params_, test_acc


def tune_random_forest(X_train, y_train, X_test, y_test):
    """Tune Random Forest hyperparameters."""
    print("\n=== Tuning Random Forest ===")
    
    param_distributions = {
        'n_estimators': [100, 200, 300, 500],
        'max_depth': [5, 10, 15, 20, None],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4],
        'max_features': ['sqrt', 'log2', None],
        'bootstrap': [True, False]
    }
    
    rf = RandomForestClassifier(random_state=42, n_jobs=-1)
    random_search = RandomizedSearchCV(
        rf, param_distributions, n_iter=20, cv=5, 
        scoring='accuracy', n_jobs=-1, verbose=1, random_state=42
    )
    
    print("Running randomized search...")
    random_search.fit(X_train, y_train)
    
    print(f"\nBest parameters: {random_search.best_params_}")
    print(f"Best CV score: {random_search.best_score_:.4f}")
    
    # Test on held-out data
    y_pred = random_search.best_estimator_.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    test_auc = roc_auc_score(y_test, random_search.best_estimator_.predict_proba(X_test)[:, 1])
    
    print(f"Test accuracy: {test_acc:.4f}")
    print(f"Test AUC: {test_auc:.4f}")
    
    return random_search.best_params_, test_acc


def tune_gradient_boosting(X_train, y_train, X_test, y_test):
    """Tune Gradient Boosting hyperparameters."""
    print("\n=== Tuning Gradient Boosting ===")
    
    param_grid = {
        'n_estimators': [100, 200, 300],
        'learning_rate': [0.01, 0.05, 0.1, 0.2],
        'max_depth': [3, 5, 7, 9],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4],
        'subsample': [0.8, 1.0]
    }
    
    gb = GradientBoostingClassifier(random_state=42)
    random_search = RandomizedSearchCV(
        gb, param_grid, n_iter=20, cv=5,
        scoring='accuracy', n_jobs=-1, verbose=1, random_state=42
    )
    
    print("Running randomized search...")
    random_search.fit(X_train, y_train)
    
    print(f"\nBest parameters: {random_search.best_params_}")
    print(f"Best CV score: {random_search.best_score_:.4f}")
    
    # Test on held-out data
    y_pred = random_search.best_estimator_.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    test_auc = roc_auc_score(y_test, random_search.best_estimator_.predict_proba(X_test)[:, 1])
    
    print(f"Test accuracy: {test_acc:.4f}")
    print(f"Test AUC: {test_auc:.4f}")
    
    return random_search.best_params_, test_acc


def tune_xgboost(X_train, y_train, X_test, y_test):
    """Tune XGBoost hyperparameters."""
    if not HAS_XGB:
        print("XGBoost not available")
        return None, None
    
    print("\n=== Tuning XGBoost ===")
    
    param_distributions = {
        'n_estimators': [100, 200, 300, 500],
        'max_depth': [3, 5, 7, 9],
        'learning_rate': [0.01, 0.05, 0.1, 0.2],
        'subsample': [0.6, 0.8, 1.0],
        'colsample_bytree': [0.6, 0.8, 1.0],
        'min_child_weight': [1, 3, 5],
        'gamma': [0, 0.1, 0.2]
    }
    
    xgb_clf = xgb.XGBClassifier(random_state=42, eval_metric='logloss', verbosity=0)
    random_search = RandomizedSearchCV(
        xgb_clf, param_distributions, n_iter=20, cv=5,
        scoring='accuracy', n_jobs=-1, verbose=1, random_state=42
    )
    
    print("Running randomized search...")
    random_search.fit(X_train, y_train)
    
    print(f"\nBest parameters: {random_search.best_params_}")
    print(f"Best CV score: {random_search.best_score_:.4f}")
    
    # Test on held-out data
    y_pred = random_search.best_estimator_.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    test_auc = roc_auc_score(y_test, random_search.best_estimator_.predict_proba(X_test)[:, 1])
    
    print(f"Test accuracy: {test_acc:.4f}")
    print(f"Test AUC: {test_auc:.4f}")
    
    return random_search.best_params_, test_acc


def main():
    parser = argparse.ArgumentParser(description='Tune hyperparameters for AFL prediction models')
    parser.add_argument('--model', default='all', 
                       choices=['logistic', 'random_forest', 'gradient_boosting', 'xgboost', 'all'],
                       help='Model to tune (default: all)')
    
    args = parser.parse_args()
    
    print("=== Hyperparameter Tuning for AFL Prediction ===\n")
    
    # Load data
    engine = get_engine()
    session = get_session(engine)
    
    print("Loading data...")
    all_matches = session.query(Match).filter(
        Match.home_score != None,
        Match.away_score != None
    ).order_by(Match.season, Match.match_id).all()
    
    # Split: train on 1990-2024, test on 2025
    train_matches = [m for m in all_matches if m.season and int(m.season) < 2025]
    test_matches = [m for m in all_matches if m.season and int(m.season) == 2025]
    
    print(f"Training matches (1990-2024): {len(train_matches)}")
    print(f"Test matches (2025): {len(test_matches)}")
    
    print("\nBuilding feature matrices...")
    train_df = build_feature_matrix(session, train_matches)
    test_df = build_feature_matrix(session, test_matches)
    
    meta_cols = {'match_id', 'label'}
    feature_cols = [c for c in train_df.columns if c not in meta_cols]
    
    X_train = train_df[feature_cols].fillna(0).values
    y_train = train_df['label'].values
    X_test = test_df[feature_cols].fillna(0).values
    y_test = test_df['label'].values
    
    print(f"Features: {len(feature_cols)}")
    print(f"Training samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")
    
    # Tune models
    results = {}
    
    if args.model in ['logistic', 'all']:
        params, acc = tune_logistic_regression(X_train, y_train, X_test, y_test)
        results['logistic'] = {'params': params, 'accuracy': acc}
    
    if args.model in ['random_forest', 'all']:
        params, acc = tune_random_forest(X_train, y_train, X_test, y_test)
        results['random_forest'] = {'params': params, 'accuracy': acc}
    
    if args.model in ['gradient_boosting', 'all']:
        params, acc = tune_gradient_boosting(X_train, y_train, X_test, y_test)
        results['gradient_boosting'] = {'params': params, 'accuracy': acc}
    
    if args.model in ['xgboost', 'all'] and HAS_XGB:
        params, acc = tune_xgboost(X_train, y_train, X_test, y_test)
        results['xgboost'] = {'params': params, 'accuracy': acc}
    
    # Summary
    print("\n" + "="*60)
    print("=== TUNING SUMMARY ===")
    print("="*60)
    
    for model_name, result in results.items():
        if result['accuracy'] is not None:
            print(f"\n{model_name.upper()}:")
            print(f"  Test Accuracy: {result['accuracy']:.4f}")
            print(f"  Best Parameters:")
            for param, value in result['params'].items():
                print(f"    {param}: {value}")
    
    # Save results
    output_file = Path('models') / 'hyperparameter_tuning_results.txt'
    with open(output_file, 'w') as f:
        f.write("=== HYPERPARAMETER TUNING RESULTS ===\n\n")
        for model_name, result in results.items():
            if result['accuracy'] is not None:
                f.write(f"{model_name.upper()}:\n")
                f.write(f"  Test Accuracy: {result['accuracy']:.4f}\n")
                f.write(f"  Best Parameters:\n")
                for param, value in result['params'].items():
                    f.write(f"    {param}: {value}\n")
                f.write("\n")
    
    print(f"\nResults saved to {output_file}")


if __name__ == '__main__':
    main()
