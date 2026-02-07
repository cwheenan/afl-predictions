from afl_predictions.db import get_engine, get_session, Match

def main():
    engine = get_engine()
    session = get_session(engine)
    rows = session.query(Match).filter(Match.season==2015).order_by(Match.round, Match.match_id).all()
    print('total 2015 matches in DB:', len(rows))
    for m in rows:
        print(m.match_id, m.season, m.round, m.home_team, 'v', m.away_team)

if __name__ == '__main__':
    main()
