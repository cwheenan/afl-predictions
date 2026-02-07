from afl_predictions.db import get_engine, get_session, Match

def main():
    engine = get_engine()
    session = get_session(engine)
    
    print("Year-by-year match counts:")
    print("-" * 30)
    for year in range(1990, 2026):
        count = session.query(Match).filter(Match.season == year).count()
        if count > 0:
            print(f'{year}: {count} matches')
    
    total = session.query(Match).count()
    print("-" * 30)
    print(f'Total matches: {total}')

if __name__ == '__main__':
    main()
