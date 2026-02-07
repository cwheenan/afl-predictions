#!/usr/bin/env python3
"""Randomized hyperparameter search for XGBoost using temporal CV (leave-one-season-out).

Saves:
 - models/hparam_random_search_{train_start}_{train_end}_{test}.json
 - models/xgb_random_best_{train_start}_{train_end}_{test}.joblib

Usage:
  python scripts/xgb_random_search.py --train-years 1990-1994 --test-year 1995 --models-dir models --n_iter 60
"""
import argparse
import json
import os
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import RandomizedSearchCV
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
import joblib
import time

try:
    import xgboost as xgb
except Exception:
    xgb = None

from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match


def build_dataset(session):
    rows = session.query(Match).filter(Match.home_score != None, Match.away_score != None).all()
    data = []
    for m in rows:
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
        row['label'] = 1 if (m.home_score is not None and m.away_score is not None and m.home_score > m.away_score) else 0
        data.append(row)
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df = df.dropna(subset=['season'])
    df['season'] = df['season'].astype(int)
    return df


def parse_years_arg(s):
    parts = []
    for token in s.split(','):
        token = token.strip()
        if '-' in token:
            a, b = token.split('-', 1)
            parts.extend(list(range(int(a), int(b) + 1)))
        else:
            parts.append(int(token))
    return sorted(set(parts))


def run(train_years, test_year, models_dir, n_iter=60, random_state=42):
    if xgb is None:
        print('xgboost not available in this environment; aborting hyperparameter search.')
        return 1

    engine = get_engine()
    session = get_session(engine)
    df = build_dataset(session)
    if df.empty:
        print('No labeled matches found in DB')
        return 1

    feature_cols = [c for c in df.columns if c not in {'match_id', 'token', 'season', 'label'}]
    train_df = df[df['season'].isin(train_years)].reset_index(drop=True)
    test_df = df[df['season'] == test_year]
    print(f'train rows: {len(train_df)}, test rows: {len(test_df)}')
    if train_df.empty or test_df.empty:
        print('Empty train or test set for the requested years')
        return 1

    X = train_df[feature_cols].fillna(0).values
    y = train_df['label'].values

    # build leave-one-season-out CV (within train_years)
    cv_splits = []
    for s in train_years:
        val_idx = list(train_df[train_df['season'] == s].index)
        train_idx = list(train_df[train_df['season'] != s].index)
        if len(val_idx) == 0:
            continue
        cv_splits.append((np.array(train_idx), np.array(val_idx)))

    if not cv_splits:
        print('No CV splits created (train years may be missing).')
        return 1

    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('xgb', xgb.XGBClassifier(use_label_encoder=False, verbosity=0))
    ])

    # Parameter distributions / candidate lists
    param_dist = {
        'xgb__max_depth': [3, 4, 5, 6, 7, 8],
        'xgb__n_estimators': [50, 100, 200, 300, 500],
        'xgb__learning_rate': [0.001, 0.01, 0.02, 0.05, 0.1],
        'xgb__subsample': [0.6, 0.7, 0.8, 0.9, 1.0],
        'xgb__colsample_bytree': [0.6, 0.7, 0.8, 0.9, 1.0],
        'xgb__gamma': [0, 0.1, 0.5, 1.0],
        'xgb__reg_alpha': [0, 0.01, 0.1, 1.0],
        'xgb__reg_lambda': [0.5, 1.0, 2.0]
    }

    print(f'Running RandomizedSearchCV with n_iter={n_iter} and {len(cv_splits)} CV folds ({len(param_dist)} param grids)')
    rs = RandomizedSearchCV(pipeline, param_distributions=param_dist, n_iter=n_iter, cv=cv_splits, scoring='roc_auc', n_jobs=-1, verbose=2, random_state=random_state)

    t0 = time.time()
    rs.fit(X, y)
    t1 = time.time()
    print('Randomized search completed in', round(t1 - t0, 1), 's')

    best_params = rs.best_params_
    best_score = rs.best_score_
    print('Best params:', best_params)
    print('Best CV AUC:', best_score)

    best_clf = rs.best_estimator_

    # evaluate best model on holdout test_year
    X_test = test_df[feature_cols].fillna(0).values
    y_test = test_df['label'].values
    X_train_full = train_df[feature_cols].fillna(0).values
    y_train_full = train_df['label'].values

    # retrain on full training set
    best_clf.fit(X_train_full, y_train_full)
    p_test = best_clf.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, (p_test >= 0.5).astype(int))
    auc = roc_auc_score(y_test, p_test) if len(np.unique(y_test)) > 1 else float('nan')
    brier = brier_score_loss(y_test, p_test)

    # save results and model
    os.makedirs(models_dir, exist_ok=True)
    out = {
        'train_years': train_years,
        'test_year': test_year,
        'n_train': len(train_df),
        'n_test': len(test_df),
        'best_params': {k.replace('xgb__',''): v for k, v in best_params.items()},
        'best_cv_auc': float(best_score),
        'test_metrics': {'acc': float(acc), 'auc': float(auc), 'brier': float(brier)},
        'search_time_sec': float(t1 - t0),
        'n_iter': int(n_iter)
    }
    out_path = os.path.join(models_dir, f'hparam_random_search_{train_years[0]}_{train_years[-1]}_{test_year}.json')
    with open(out_path, 'w', encoding='utf8') as fh:
        json.dump(out, fh, indent=2)

    model_path = os.path.join(models_dir, f'xgb_random_best_{train_years[0]}_{train_years[-1]}_{test_year}.joblib')
    joblib.dump(best_clf, model_path)

    print('Saved search results to', out_path)
    print('Saved best model to', model_path)
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--train-years', required=True)
    p.add_argument('--test-year', type=int, required=True)
    p.add_argument('--models-dir', default='models')
    p.add_argument('--n_iter', type=int, default=60)
    p.add_argument('--seed', type=int, default=42)
    args = p.parse_args()
    train_years = parse_years_arg(args.train_years)
    exit(run(train_years, args.test_year, args.models_dir, n_iter=args.n_iter, random_state=args.seed))
