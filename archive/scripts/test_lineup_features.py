"""Small smoke test for lineup feature functions.

Runs a few functions against the processed DB and prints sample outputs.
"""
from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import (
    recency_weighted_presence,
    expected_squad_probs,
    player_recent_stats,
    assemble_player_features,
)


def main():
    engine = get_engine()
    session = get_session(engine)
    m = session.query(Match).first()
    if not m:
        print('no matches in DB')
        return
    print('testing for match_id', m.match_id, 'season', m.season, 'round', m.round)

    probs = expected_squad_probs(session, m.match_id)
    print('expected squad probs (sample 10):')
    for i, (pid, p) in enumerate(probs.items()):
        print(pid, p)
        if i >= 9:
            break

    print('\nassemble player features (sample 10):')
    feats = assemble_player_features(session, m.match_id)
    for i, (pid, f) in enumerate(feats.items()):
        print(pid, f)
        if i >= 9:
            break


if __name__ == '__main__':
    main()
