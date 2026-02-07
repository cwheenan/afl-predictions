"""Sanity-check pipeline: ingest a small window of rounds, train a simple model,
predict the next round, and print evaluation metrics.

This is intentionally lightweight and self-contained. It uses the processed DB
at `config.DB_URL` and `sklearn` logistic regression as a baseline.

Usage: python scripts/sanity_check_pipeline.py
"""
from collections import defaultdict
import math
import sys

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
import numpy as np

from afl_predictions.db import get_engine, get_session, Match, PlayerStats
from afl_predictions.features.lineup import features_for_match, match_level_vector
from afl_predictions import config


def matches_by_season_round(session):
    rows = session.query(Match).order_by(Match.season, Match.round, Match.match_id).all()
    by_season = defaultdict(lambda: defaultdict(list))
    for m in rows:
        by_season[m.season][m.round].append(m)
    return by_season


def build_dataset(session, matches):
    X = []
    y = []
    mids = []
    for m in matches:
        try:
            vec, names = match_level_vector(session, m.match_id)
        except Exception:
            continue
        # label: home win. If stored scores are missing, try to aggregate from player_stats
        home_score = m.home_score
        away_score = m.away_score
        if home_score is None or away_score is None:
            # aggregate goals/behinds from player_stats for the match
            rows = session.query(PlayerStats).filter(PlayerStats.match_id == m.match_id).all()
            h_goals = h_behinds = a_goals = a_behinds = 0
            for r in rows:
                if not r.team:
                    continue
                # try player-level goals/behinds
                g = int(r.goals) if r.goals not in (None, '') else 0
                b = int(r.behinds) if r.behinds not in (None, '') else 0
                if r.team == m.home_team:
                    h_goals += g
                    h_behinds += b
                elif r.team == m.away_team:
                    a_goals += g
                    a_behinds += b
            # convert to points
            home_score = h_goals * 6 + h_behinds
            away_score = a_goals * 6 + a_behinds
        label = 1 if (home_score > away_score) else 0
        X.append(vec)
        y.append(label)
        mids.append(m.match_id)

    feature_names = names if X else []
    return np.array(X, dtype=float), np.array(y, dtype=int), feature_names, mids


def run(window_rounds=5):
    engine = get_engine()
    session = get_session(engine)

    by_season = matches_by_season_round(session)
    # pick a season with enough rounds
    season = None
    rounds = None
    for s, rounds_map in sorted(by_season.items(), reverse=True):
        if len(rounds_map) >= window_rounds + 1:
            season = s
            rounds = sorted(rounds_map.keys())
            break
    if season is None:
        # fallback: use all matches available and split by match_id order
        print('No season with enough rounds available; falling back to all matches split')
        all_matches = session.query(Match).order_by(Match.match_id).all()
        if len(all_matches) < 2:
            print('Not enough total matches in DB for fallback sanity check (need >=2)')
            return
        # use 80/20 split
        cut = int(round(len(all_matches) * 0.8))
        train_matches = all_matches[:cut]
        test_matches = all_matches[cut:]
        X_train, y_train, feature_names, _ = build_dataset(session, train_matches)
        X_test, y_test, _, mids = build_dataset(session, test_matches)
        # if we have only a few matches (<6), do cross-validation instead
        from sklearn.model_selection import cross_val_score, StratifiedKFold

        X_all, y_all, feature_names, mids_all = build_dataset(session, all_matches)
        if X_all.size == 0:
            print('Not enough featureful matches to run fallback CV — aborting')
            return

        n = len(y_all)
        cv = 3 if n >= 3 else n
        if cv < 2:
            print('Not enough data for cross-validation folds — need at least 2 examples')
            return

        print(f'Performing cross-validation on {n} matches with {cv}-fold CV')
        clf = LogisticRegression(max_iter=200)
        # simple scaling before CV: use pipeline-like manual scaling per fold via wrapper
        def score_with_scaling(estimator, X, y, cv):
            skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=1)
            scores = []
            for train_idx, test_idx in skf.split(X, y):
                Xtr, Xte = X[train_idx], X[test_idx]
                ytr, yte = y[train_idx], y[test_idx]
                mu = Xtr.mean(axis=0)
                sigma = Xtr.std(axis=0)
                sigma[sigma == 0] = 1.0
                Xtr_s = (Xtr - mu) / sigma
                Xte_s = (Xte - mu) / sigma
                estimator.fit(Xtr_s, ytr)
                scores.append(estimator.score(Xte_s, yte))
            return scores

        scores = score_with_scaling(clf, X_all, y_all, cv)
        print(f'CV scores: {scores} mean={sum(scores)/len(scores):.3f}')
        return

    # pick a contiguous block: first window_rounds rounds for training, next round for test
    train_rounds = rounds[:window_rounds]
    test_round = rounds[window_rounds]

    print(f'Using season={season}, train_rounds={train_rounds}, test_round={test_round}')

    train_matches = []
    for r in train_rounds:
        train_matches.extend(by_season[season][r])
    test_matches = by_season[season][test_round]

    X_train, y_train, feature_names, _ = build_dataset(session, train_matches)
    X_test, y_test, _, mids = build_dataset(session, test_matches)

    if X_train.size == 0 or X_test.size == 0:
        print('Not enough data to train/test — aborting')
        return

    print('Feature names:', feature_names)
    print('Train size:', X_train.shape, 'Test size:', X_test.shape)

    # simple scaling: mean/std from train
    mu = X_train.mean(axis=0)
    sigma = X_train.std(axis=0)
    sigma[sigma == 0] = 1.0
    X_train_s = (X_train - mu) / sigma
    X_test_s = (X_test - mu) / sigma

    clf = LogisticRegression(max_iter=200)
    clf.fit(X_train_s, y_train)
    preds = clf.predict(X_test_s)

    acc = accuracy_score(y_test, preds)
    print(f'Test accuracy: {acc:.3f} ({len(y_test)} matches)')

    for mid, pred, actual in zip(mids, preds, y_test):
        print(f'match {mid}: pred_home_win={pred} actual_home_win={actual}')


if __name__ == '__main__':
    run(window_rounds=5)
