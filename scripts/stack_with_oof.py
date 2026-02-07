#!/usr/bin/env python3
"""Train stacking meta-learner with out-of-fold predictions (leave-one-season-out CV).

Produces:
 - models/stacking_eval_1990_1994_1995.json
 - models/predictions_1990_1994_1995_stacked.csv

Usage: python scripts/stack_with_oof.py --train-years 1990-1994 --test-year 1995
"""
import argparse
import json
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss, confusion_matrix

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


def run_stack(train_years, test_year, out_dir):
    engine = get_engine()
    session = get_session(engine)
    df = build_dataset(session)
    if df.empty:
        print('No labeled matches found in DB')
        return 1
    feature_cols = [c for c in df.columns if c not in {'match_id', 'token', 'season', 'label'}]
    train_df = df[df['season'].isin(train_years)].reset_index(drop=True)
    test_df = df[df['season'] == test_year].reset_index(drop=True)
    print(f'train rows: {len(train_df)}, test rows: {len(test_df)}')
    if train_df.empty or test_df.empty:
        print('Empty train or test set for the requested years')
        return 1

    X = train_df[feature_cols].fillna(0).values
    y = train_df['label'].values
    seasons = train_df['season'].values

    # Prepare OOF arrays
    oof_lr = np.zeros(len(train_df))
    oof_xgb = np.zeros(len(train_df))

    # Leave-one-season-out CV across train_years
    for hold in train_years:
        val_mask = (seasons == hold)
        train_mask = ~val_mask
        if val_mask.sum() == 0:
            continue
        X_tr = X[train_mask]
        y_tr = y[train_mask]
        X_val = X[val_mask]

        # standardize for LR
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_val_s = scaler.transform(X_val)

        # LR
        lr = LogisticRegression(max_iter=2000)
        lr.fit(X_tr_s, y_tr)
        oof_lr[val_mask] = lr.predict_proba(X_val_s)[:, 1]

        # XGB (use raw features)
        try:
            import xgboost as xgb
            xgb_clf = xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss')
            xgb_clf.fit(X_tr, y_tr)
            oof_xgb[val_mask] = xgb_clf.predict_proba(X_val)[:, 1]
        except Exception as e:
            print('XGBoost training failed in fold', hold, 'error:', e)
            oof_xgb[val_mask] = 0.5

    # Train base models on full train set to make test predictions
    scaler_full = StandardScaler()
    X_s_full = scaler_full.fit_transform(X)
    lr_full = LogisticRegression(max_iter=2000).fit(X_s_full, y)

    # If a prior randomized/grid search produced best params, prefer those
    xgb_params = None
    try:
        # look for randomized search JSON that our random search script writes
        import json
        cand = os.path.join('models', f'hparam_random_search_{train_years[0]}_{train_years[-1]}_{test_year}.json')
        if os.path.exists(cand):
            with open(cand, 'r', encoding='utf8') as fh:
                jr = json.load(fh)
                if 'best_params' in jr and jr['best_params']:
                    xgb_params = jr['best_params']
        # fallback to grid search JSON
        if xgb_params is None:
            cand2 = os.path.join('models', f'hparam_search_{train_years[0]}_{train_years[-1]}_{test_year}.json')
            if os.path.exists(cand2):
                with open(cand2, 'r', encoding='utf8') as fh:
                    jr = json.load(fh)
                    if 'best_params' in jr and jr['best_params']:
                        xgb_params = jr['best_params']
    except Exception:
        xgb_params = None

    try:
        import xgboost as xgb
        if xgb_params:
            # ensure keys are valid XGBClassifier args (prefixes already removed by JSON writers)
            xgb_full = xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss', **xgb_params)
        else:
            xgb_full = xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss')
        xgb_full.fit(X, y)
    except Exception as e:
        print('XGBoost full training failed:', e)
        xgb_full = None

    # Test preds from base learners
    X_test = test_df[feature_cols].fillna(0).values
    X_test_s = scaler_full.transform(X_test)
    p_lr_test = lr_full.predict_proba(X_test_s)[:, 1]
    if xgb_full is not None:
        p_xgb_test = xgb_full.predict_proba(X_test)[:, 1]
    else:
        p_xgb_test = np.full(len(X_test), 0.5)

    # Train meta-learner on OOF preds
    stack_X = np.vstack([oof_lr, oof_xgb]).T
    meta = LogisticRegression(max_iter=2000)
    meta.fit(stack_X, y)

    # Meta predictions on test
    stack_test = np.vstack([p_lr_test, p_xgb_test]).T
    p_meta_test = meta.predict_proba(stack_test)[:, 1]

    # Evaluate
    y_test = test_df['label'].values
    def eval_probs(y, p):
        acc = ( (p >= 0.5) == y ).mean()
        auc = roc_auc_score(y, p) if len(np.unique(y)) > 1 else float('nan')
        brier = brier_score_loss(y, p)
        cm = confusion_matrix(y, (p >= 0.5).astype(int)).tolist()
        return {'acc': float(acc), 'auc': float(auc), 'brier': float(brier), 'confusion': cm}

    from sklearn.metrics import roc_auc_score, brier_score_loss, confusion_matrix

    results = {
        'train_years': train_years,
        'test_year': test_year,
        'n_train': len(train_df),
        'n_test': len(test_df),
        'lr': eval_probs(y_test, p_lr_test),
        'xgb': eval_probs(y_test, p_xgb_test),
        'meta': eval_probs(y_test, p_meta_test)
    }

    os.makedirs(out_dir, exist_ok=True)
    out_json = os.path.join(out_dir, f'stacking_eval_{train_years[0]}_{train_years[-1]}_{test_year}.json')
    with open(out_json, 'w', encoding='utf8') as fh:
        json.dump(results, fh, indent=2)

    # Save predictions CSV with base and meta probs for test
    test_out = test_df.copy()
    test_out['prob_lr'] = p_lr_test
    test_out['prob_xgb'] = p_xgb_test
    test_out['prob_meta'] = p_meta_test
    out_csv = os.path.join(out_dir, f'predictions_{train_years[0]}_{train_years[-1]}_{test_year}_stacked.csv')
    test_out.to_csv(out_csv, index=False)

    print('Saved stacking eval to', out_json)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--train-years', required=True)
    p.add_argument('--test-year', type=int, required=True)
    p.add_argument('--out-dir', default='models')
    args = p.parse_args()
    train_years = parse_years_arg(args.train_years)
    exit(run_stack(train_years, args.test_year, args.out_dir))
