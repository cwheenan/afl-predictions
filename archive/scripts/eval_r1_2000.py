"""Evaluate trained model on Round 1, 2000 matches.

Writes per-match predictions to models/predictions_2000_r1.csv and prints
accuracy, AUC (if computable), and Brier score.
"""
import csv
import json
import numpy as np
from joblib import load
from sqlalchemy import and_
from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import features_for_match
from sklearn.metrics import roc_auc_score, brier_score_loss, accuracy_score


def main():
    engine = get_engine()
    session = get_session(engine)

    # fetch matches for season 2000; filter for round==1
    qs = session.query(Match).filter(Match.season == 2000).all()
    matches_r1 = [m for m in qs if m.round is not None and str(m.round).strip().lstrip('Rr').split()[0] in ('1', '01')]
    print(f'Found {len(matches_r1)} matches for season 2000 round 1')
    if not matches_r1:
        return

    X = []
    ids = []
    tokens = []
    rows_meta = []
    for m in matches_r1:
        try:
            fv = features_for_match(session, m.match_id)
            # ensure deterministic order matching saved feature_names.json
            names = [
                "diff_goals",
                "diff_behinds",
                "diff_kicks",
                "diff_handballs",
                "diff_disposals",
                "diff_marks",
                "diff_tackles",
                "diff_hitouts",
                "diff_frees_for",
                "diff_frees_against",
                "diff_avg_percent_played",
                "home_players",
                "away_players",
                "home_recent_margin",
                "away_recent_margin",
                "diff_recent_margin",
            ]
            vec = [float(fv.get(n, 0.0)) for n in names]
        except Exception as e:
            print('Failed to build features for match', m.match_id, m.token, 'err', e)
            continue
        X.append(vec)
        ids.append(m.match_id)
        tokens.append(m.token)
        rows_meta.append((m.home_team, m.away_team, m.home_score, m.away_score))

    if not X:
        print('No feature vectors built; aborting')
        return

    X_arr = np.array(X)
    model = load('models/xgb_final.joblib')
    if hasattr(model, 'predict_proba'):
        probs = model.predict_proba(X_arr)[:, 1]
    else:
        # fallback to direct predict (may be probabilities already)
        probs = model.predict(X_arr)

    # derive true labels
    y = []
    for (_, _, hs, ascore) in rows_meta:
        if hs is None or ascore is None:
            y.append(None)
        else:
            y.append(1 if hs > ascore else 0)

    valid_idx = [i for i, v in enumerate(y) if v is not None]
    if not valid_idx:
        print('No labeled matches to evaluate; saving predictions only')
    else:
        probs_eval = probs[valid_idx]
        y_eval = [y[i] for i in valid_idx]
        preds = [1 if p >= 0.5 else 0 for p in probs_eval]
        acc = accuracy_score(y_eval, preds)
        try:
            auc = roc_auc_score(y_eval, probs_eval) if len(set(y_eval)) > 1 else float('nan')
        except Exception:
            auc = float('nan')
        brier = brier_score_loss(y_eval, probs_eval)
        print(f'R1-2000: n={len(y_eval)} acc={acc:.4f} auc={auc} brier={brier:.4f}')

    # save per-match CSV
    outf = 'models/predictions_2000_r1.csv'
    with open(outf, 'w', newline='', encoding='utf8') as fh:
        w = csv.writer(fh)
        w.writerow(['match_id', 'token', 'home_team', 'away_team', 'home_score', 'away_score', 'prob_home_win', 'pred'])
        for idx_in_list, mid in enumerate(ids):
            m_home, m_away, m_hs, m_as = rows_meta[idx_in_list]
            prob = float(probs[idx_in_list])
            pred = 1 if prob >= 0.5 else 0
            w.writerow([mid, tokens[idx_in_list], m_home, m_away, m_hs, m_as, prob, pred])
    print('Saved predictions to', outf)


if __name__ == '__main__':
    main()
