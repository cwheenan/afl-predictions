from afl_predictions.db import get_engine, get_session, Match

def main():
    engine = get_engine()
    session = get_session(engine)
    seasons = list(range(1990, 1995))
    total = 0
    print('season,count')
    for s in seasons:
        cnt = session.query(Match).filter(Match.season == s).count()
        print(f'{s},{cnt}')
        total += cnt
    print('total_matches_in_1990_1994,', total)

if __name__ == '__main__':
    main()
