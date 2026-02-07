"""Diagnostics for a temporal split: class balance and per-feature summaries.

Saves results to models/diagnose_<train-start>_<train-end>_<test>.json
"""
import argparse
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

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


def summarize(df, feature_cols):
    out = {}
    # class balance
    counts = df['label'].value_counts().to_dict()
    # convert label keys to plain python strings for JSON safety
    out['counts'] = {str(int(k)): int(v) for k, v in counts.items()}
    # per-feature mean/std per class
    stats = {}
    for c in sorted(df['label'].unique()):
        sub = df[df['label'] == c]
        # use string keys for class labels
        stats[str(int(c))] = {
            'n': int(len(sub)),
            'means': sub[feature_cols].mean().to_dict(),
            'stds': sub[feature_cols].std().fillna(0).to_dict()
        }
    out['per_class'] = stats
    # difference in means
    if set([0,1]).issubset(set(df['label'].unique())):
        m0 = df[df['label']==0][feature_cols].mean()
        m1 = df[df['label']==1][feature_cols].mean()
        diff = (m1 - m0).abs().sort_values(ascending=False)
        out['top_diff_features'] = diff.head(10).to_dict()
    else:
        out['top_diff_features'] = {}
    return out


def run(train_years, test_year, models_dir):
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

    report = {
        'train_years': train_years,
        'test_year': test_year,
        'n_train': len(train_df),
        'n_test': len(test_df),
    }
    if len(train_df) > 0:
        report['train'] = summarize(train_df, feature_cols)
        # zero-variance features in train
        try:
            z = train_df[feature_cols].var()
            report['train_zero_variance'] = [f for f, v in z.items() if float(v) == 0.0]
        except Exception:
            report['train_zero_variance'] = []
    else:
        report['train'] = {}
    if len(test_df) > 0:
        report['test'] = summarize(test_df, feature_cols)
        try:
            zt = test_df[feature_cols].var()
            report['test_zero_variance'] = [f for f, v in zt.items() if float(v) == 0.0]
        except Exception:
            report['test_zero_variance'] = []
    else:
        report['test'] = {}

    os.makedirs(models_dir, exist_ok=True)
    out_path = os.path.join(models_dir, f'diagnose_{{train_years[0]}}_{{train_years[-1]}}_{{test_year}}.json')
    with open(out_path, 'w', encoding='utf8') as fh:
        json.dump(report, fh, indent=2, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else x)

    print('Saved diagnostic to', out_path)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--train-years', required=True, help='Comma list or range, e.g. 1990-1994 or single year 1990')
    p.add_argument('--test-year', type=int, required=True)
    p.add_argument('--models-dir', default='models')
    args = p.parse_args()
    # parse train years similarly to eval script
    def parse_years(s):
        parts = []
        for token in s.split(','):
            token = token.strip()
            if '-' in token:
                a,b = token.split('-',1)
                parts.extend(list(range(int(a), int(b)+1)))
            else:
                parts.append(int(token))
        return sorted(set(parts))
    train_years = parse_years(args.train_years)
    exit(run(train_years, args.test_year, args.models_dir))
