"""Train on 2015 rounds 3-5 and predict Geelong vs Collingwood (round 6) using only prior rounds.

Important: this script will NOT read or use any round-6 data. It trains on matches from
rounds 3,4,5 of season 2015 and constructs aggregated team features from those matches
to predict the head-to-head outcome for Geelong (home) vs Collingwood (away).
"""
from collections import defaultdict
import numpy as np
from sklearn.linear_model import LogisticRegression

from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import team_weighted_features, match_level_vector


def get_train_matches(session, season=2015, rounds=(3,4,5)):
    return session.query(Match).filter(Match.season==season, Match.round.in_(rounds)).all()


def avg_dicts(dicts):
    if not dicts:
        return {}
    keys = set().union(*[set(d.keys()) for d in dicts])
    out = {}
    for k in keys:
        vals = [d.get(k, 0.0) for d in dicts]
        out[k] = float(sum(vals) / len(vals))
    return out


def build_team_aggregate(session, matches, team_name):
    # for each match where team_name is home or away, compute team_weighted_features and select home/away part
    aggs = []
    for m in matches:
        if m.home_team == team_name or m.away_team == team_name:
            tw = team_weighted_features(session, m.match_id)
            # filter keys for this team
            if m.home_team == team_name:
                prefix = 'home_'
            else:
                prefix = 'away_'
            # extract keys belonging to the team
            team_keys = {k[len(prefix):]: v for k, v in tw.items() if k.startswith(prefix)}
            # normalize names to same schema as team_weighted_features subdict
            aggs.append(team_keys)
    return avg_dicts(aggs)


def build_feature_vector_from_team_aggs(home_agg, away_agg, feature_names):
    # recompose the full feature dict used by match_level_vector (home_..., away_, diff_... and counts)
    fv = {}
    # counts
    fv['home_player_count'] = int(home_agg.get('player_count', 0)) if home_agg else 0
    fv['away_player_count'] = int(away_agg.get('player_count', 0)) if away_agg else 0
    # weighted stats keys (recent goals,disposals,kicks,marks,tackles)
    keys = ['wt_recent_goals', 'wt_recent_disposals', 'wt_recent_kicks', 'wt_recent_marks', 'wt_recent_tackles']
    # but in team_agg returned earlier keys were like 'wt_recent_goals' under 'home_wt_recent_goals'
    # here home_agg/away_agg keys are the stripped versions (no prefix)
    for base in ['wt_recent_goals', 'wt_recent_disposals', 'wt_recent_kicks', 'wt_recent_marks', 'wt_recent_tackles']:
        fv[f'home_{base}'] = float(home_agg.get(base, 0.0))
        fv[f'away_{base}'] = float(away_agg.get(base, 0.0))
        fv[f'diff_{base}'] = fv[f'home_{base}'] - fv[f'away_{base}']

    # Ensure ordering consistent with feature_names
    vec = [float(fv.get(n, 0.0)) for n in feature_names]
    return vec


def main():
    engine = get_engine()
    session = get_session(engine)

    # get training matches (only rounds 3,4,5 of 2015)
    train_matches = get_train_matches(session, season=2015, rounds=(3,4,5))
    print('train matches found:', len(train_matches))
    if not train_matches:
        print('No training matches available for 2015 rounds 3-5 in DB. Aborting.')
        return

    # build training dataset
    X = []
    y = []
    names = None
    mids = []
    for m in train_matches:
        try:
            vec, names = match_level_vector(session, m.match_id)
        except Exception as e:
            print('skip match', m.match_id, 'err', e)
            continue
        # derive label from stored scores or aggregated player_stats
        home_score = m.home_score
        away_score = m.away_score
        if home_score is None or away_score is None:
            # aggregate from player_stats
            rows = session.query(Match).filter(Match.match_id == m.match_id).all()
            # if still missing, skip
            if home_score is None or away_score is None:
                print('missing scores for match', m.match_id, 'skipping label')
                continue
        label = 1 if (home_score > away_score) else 0
        X.append(vec)
        y.append(label)
        mids.append(m.match_id)

    if not X:
        print('No training vectors built — aborting')
        return

    X = np.array(X, dtype=float)
    y = np.array(y, dtype=int)
    print('X shape', X.shape, 'y shape', y.shape)

    # train simple logistic regression
    clf = LogisticRegression(max_iter=200)
    clf.fit(X, y)
    print('trained classifier on', len(y), 'matches')

    # Build aggregated team features for Geelong (home) and Collingwood (away)
    HOME = 'Geelong'
    AWAY = 'Collingwood'
    home_agg = build_team_aggregate(session, train_matches, HOME)
    away_agg = build_team_aggregate(session, train_matches, AWAY)

    if not home_agg and not away_agg:
        print('No historical data for either team in rounds 3-5 — cannot form prediction')
        return

    # reconstruct feature_names used in training
    feature_names = sorted(names)
    pred_vec = build_feature_vector_from_team_aggs(home_agg, away_agg, feature_names)
    import numpy as _np
    pred_arr = _np.array(pred_vec, dtype=float).reshape(1, -1)
    prob = clf.predict_proba(pred_arr)[0][1]
    pred_label = clf.predict(pred_arr)[0]

    print(f'Prediction for {HOME} (home) vs {AWAY} (away) — P(home_win) = {prob:.3f} label={pred_label}')


if __name__ == '__main__':
    main()
