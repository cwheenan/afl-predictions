"""Simple DB inspector to print counts and sample rows for debugging the sanity-check."""
from afl_predictions.db import get_engine, get_session, Match, PlayerStats


def main():
    engine = get_engine()
    session = get_session(engine)
    print('matches:', session.query(Match).count())
    print('player_stats:', session.query(PlayerStats).count())
    print('\nsample matches:')
    for m in session.query(Match).limit(5):
        print(m.match_id, m.season, m.round, m.home_team, m.away_team, m.home_score, m.away_score)
    print('\nsample player_stats rows:')
    for p in session.query(PlayerStats).limit(5):
        print('id', p.id, 'match_id', p.match_id, 'player_id', p.player_id, 'team', p.team, 'named', p.named, 'percent_played', p.percent_played)


if __name__ == '__main__':
    main()
