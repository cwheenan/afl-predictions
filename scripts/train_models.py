"""Train baseline models (LogisticRegression, XGBoost) on parsed AFL data.

Produces CV results using season-based temporal splits and saves final XGBoost
model artifact and feature names under `models/`.

Usage:
  python scripts/train_models.py --db data/processed/afl.db --models-dir models --save-model
  python scripts/train_models.py --predict --token <token>
"""
import argparse
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
from sklearn.preprocessing import StandardScaler
from joblib import dump, load

from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match


def build_dataset(session):
    """Build feature matrix X and labels y from processed DB.

    Returns: DataFrame with features, labels, season, match_id, token
    """
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
        # label: 1 if home win, 0 otherwise (draw counted as 0)
        try:
            row['label'] = 1 if (m.home_score is not None and m.away_score is not None and m.home_score > m.away_score) else 0
        except Exception:
            continue
        data.append(row)

    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    # drop rows with no season
    df = df.dropna(subset=['season'])
    df['season'] = df['season'].astype(int)
    return df


def temporal_cv(df, feature_cols):
    """Perform season-based temporal CV: for each season t, train on seasons < t, test on season t."""
    seasons = sorted(df['season'].unique())
    results = []
    for i, s in enumerate(seasons):
        train_df = df[df['season'] < s]
        test_df = df[df['season'] == s]
        if train_df.empty or test_df.empty:
            continue
        X_train = train_df[feature_cols].fillna(0).values
        y_train = train_df['label'].values
        X_test = test_df[feature_cols].fillna(0).values
        y_test = test_df['label'].values

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Logistic baseline
        lr = LogisticRegression(max_iter=1000)
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

        results.append({
            'season': s,
            'lr_acc': acc_lr, 'lr_auc': auc_lr, 'lr_brier': brier_lr,
            'xgb_acc': acc_xgb, 'xgb_auc': auc_xgb, 'xgb_brier': brier_xgb,
            'n_train': len(train_df), 'n_test': len(test_df),
        })

    return pd.DataFrame(results)


def train_and_save_final(df, feature_cols, models_dir):
    X = df[feature_cols].fillna(0).values
    y = df['label'].values
    # train final XGBoost
    import xgboost as xgb
    clf = xgb.XGBClassifier(use_label_encoder=False, eval_metric='logloss')
    clf.fit(X, y)
    os.makedirs(models_dir, exist_ok=True)
    model_path = os.path.join(models_dir, 'xgb_final.joblib')
    dump(clf, model_path)
    # save feature names
    with open(os.path.join(models_dir, 'feature_names.json'), 'w', encoding='utf8') as fh:
        json.dump(feature_cols, fh)
    print('Saved final XGBoost model to', model_path)
    return model_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default=None, help='Path to processed DB (not used, uses config.DB_URL)')
    p.add_argument('--models-dir', default='models')
    p.add_argument('--save-model', action='store_true')
    p.add_argument('--predict', action='store_true')
    p.add_argument('--token', default=None)
    args = p.parse_args()

    engine = get_engine()
    session = get_session(engine)

    df = build_dataset(session)
    if df.empty:
        print('No labeled matches available in DB; run parsing first')
        return

    # feature columns: all except metadata
    meta_cols = {'match_id', 'token', 'season', 'label'}
    feature_cols = [c for c in df.columns if c not in meta_cols]

    print('Built dataset: X shape', (len(df), len(feature_cols)))
    # temporal CV
    cv_res = temporal_cv(df, feature_cols)
    if not cv_res.empty:
        print('Temporal CV results:')
        print(cv_res.describe().to_string())
    else:
        print('No temporal CV results (not enough seasons)')

    # final training
    if args.save_model:
        train_and_save_final(df, feature_cols, args.models_dir)

    # predict mode
    if args.predict and args.token:
        # load model
        model_path = os.path.join(args.models_dir, 'xgb_final.joblib')
        if not os.path.exists(model_path):
            print('No saved model found at', model_path)
            return
        clf = load(model_path)
        # build feature vector for token
        # find match by token
        m = session.query(Match).filter_by(token=args.token).first()
        if not m:
            print('Match not found for token', args.token)
            return
        fv = features_for_match(session, m.match_id)
        x = np.array([fv.get(c, 0.0) for c in feature_cols]).reshape(1, -1)
        p = clf.predict_proba(x)[0, 1]
        print('Prediction P(home_win)=', p)


if __name__ == '__main__':
    main()
