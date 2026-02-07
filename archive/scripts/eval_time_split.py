"""Evaluate temporal split: train on given seasons and test on a target season.

Usage examples:
  python scripts/eval_time_split.py --train-years 1990-1994 --test-year 1995 --models-dir models
  python scripts/eval_time_split.py --train-years 1990,1991,1992 --test-year 1993
"""
import argparse
import json
import os
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss, confusion_matrix
from sklearn.preprocessing import StandardScaler
import numpy as np

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
    import pandas as pd
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df = df.dropna(subset=['season'])
    df['season'] = df['season'].astype(int)
    return df


def parse_years_arg(s):
    # accept ranges like 1990-1994 or comma lists
    parts = []
    for token in s.split(','):
        token = token.strip()
        if '-' in token:
            a, b = token.split('-', 1)
            parts.extend(list(range(int(a), int(b) + 1)))
        else:
            parts.append(int(token))
    return sorted(set(parts))


def run_eval(train_years, test_year, models_dir):
    engine = get_engine()
    session = get_session(engine)
    df = build_dataset(session)
    if df.empty:
        print('No labeled matches found in DB')
        return 1

    feature_cols = [c for c in df.columns if c not in {'match_id', 'token', 'season', 'label'}]
    train_df = df[df['season'].isin(train_years)]
    test_df = df[df['season'] == test_year]
    print(f'train rows: {len(train_df)}, test rows: {len(test_df)}')
    if train_df.empty or test_df.empty:
        print('Empty train or test set for the requested years')
        return 1

    X_train = train_df[feature_cols].fillna(0).values
    y_train = train_df['label'].values
    X_test = test_df[feature_cols].fillna(0).values
    y_test = test_df['label'].values

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # Logistic baseline
    lr = LogisticRegression(max_iter=2000)
    lr.fit(X_train_s, y_train)
    p_lr = lr.predict_proba(X_test_s)[:, 1]
    acc_lr = accuracy_score(y_test, (p_lr >= 0.5).astype(int))
    auc_lr = roc_auc_score(y_test, p_lr) if len(np.unique(y_test)) > 1 else float('nan')
    brier_lr = brier_score_loss(y_test, p_lr)

    # XGBoost
    try:
        import xgboost as xgb
        xgb_clf = xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss')
        xgb_clf.fit(X_train, y_train)
        p_xgb = xgb_clf.predict_proba(X_test)[:, 1]
        acc_xgb = accuracy_score(y_test, (p_xgb >= 0.5).astype(int))
        auc_xgb = roc_auc_score(y_test, p_xgb) if len(np.unique(y_test)) > 1 else float('nan')
        brier_xgb = brier_score_loss(y_test, p_xgb)
    except Exception as e:
        xgb_clf = None
        acc_xgb = auc_xgb = brier_xgb = float('nan')
        p_xgb = None

    cm_lr = confusion_matrix(y_test, (p_lr >= 0.5).astype(int)).tolist()
    cm_xgb = confusion_matrix(y_test, (p_xgb >= 0.5).astype(int)).tolist() if p_xgb is not None else None

    out = {
        'train_years': train_years,
        'test_year': test_year,
        'n_train': len(train_df),
        'n_test': len(test_df),
        'lr': {'acc': acc_lr, 'auc': auc_lr, 'brier': brier_lr, 'confusion': cm_lr},
        'xgb': {'acc': acc_xgb, 'auc': auc_xgb, 'brier': brier_xgb, 'confusion': cm_xgb},
    }

    os.makedirs(models_dir, exist_ok=True)
    out_path = os.path.join(models_dir, f'eval_{{train_years[0]}}_{{train_years[-1]}}_{{test_year}}.json')
    with open(out_path, 'w', encoding='utf8') as fh:
        json.dump(out, fh, indent=2)

    print('Evaluation results saved to', out_path)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--train-years', required=True, help='Comma list or range, e.g. 1990-1994')
    p.add_argument('--test-year', type=int, required=True)
    p.add_argument('--models-dir', default='models')
    args = p.parse_args()
    train_years = parse_years_arg(args.train_years)
    exit(run_eval(train_years, args.test_year, args.models_dir))
