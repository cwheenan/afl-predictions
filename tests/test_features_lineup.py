import pytest

from afl_predictions.db import get_engine, get_session, Match
from afl_predictions.features.lineup import (
    recency_weighted_presence,
    expected_squad_probs,
    player_recent_stats,
    assemble_player_features,
    team_weighted_features,
    match_level_vector,
)


@pytest.fixture(scope='module')
def session():
    engine = get_engine()
    return get_session(engine)


def test_recency_presence(session):
    # pick a player from DB
    m = session.query(Match).first()
    assert m is not None
    # assemble features and pick a player id
    feats = assemble_player_features(session, m.match_id)
    if not feats:
        pytest.skip('no player features available')
    pid = next(iter(feats.keys()))
    p = recency_weighted_presence(session, pid)
    assert 0.0 <= p <= 1.0


def test_expected_and_assemble(session):
    m = session.query(Match).first()
    assert m is not None
    probs = expected_squad_probs(session, m.match_id)
    assert isinstance(probs, dict)
    feats = assemble_player_features(session, m.match_id)
    assert isinstance(feats, dict)


def test_team_and_vector(session):
    m = session.query(Match).first()
    assert m is not None
    tv = team_weighted_features(session, m.match_id)
    vec, names = match_level_vector(session, m.match_id)
    assert isinstance(tv, dict)
    assert isinstance(vec, list)
    assert len(vec) == len(names)
