"""Verify data integrity and completeness across all seasons."""
from afl_predictions.db import get_engine, get_session, Match
import pandas as pd

def analyze_season(session, year):
    """Analyze a single season for completeness and issues."""
    matches = session.query(Match).filter(Match.season == year).all()
    
    if not matches:
        return {
            'year': year,
            'count': 0,
            'status': 'MISSING',
            'issues': ['No data']
        }
    
    count = len(matches)
    issues = []
    
    # Check for null values in critical fields
    null_checks = {
        'home_team': sum(1 for m in matches if not m.home_team),
        'away_team': sum(1 for m in matches if not m.away_team),
        'home_score': sum(1 for m in matches if m.home_score is None),
        'away_score': sum(1 for m in matches if m.away_score is None),
        'date': sum(1 for m in matches if not m.date),
        'venue': sum(1 for m in matches if not m.venue)
    }
    
    for field, null_count in null_checks.items():
        if null_count > 0:
            issues.append(f'{null_count} matches missing {field}')
    
    # Check for duplicates
    tokens = [m.token for m in matches]
    if len(tokens) != len(set(tokens)):
        duplicates = len(tokens) - len(set(tokens))
        issues.append(f'{duplicates} duplicate tokens')
    
    # Expected match counts (approximate)
    expected_ranges = {
        range(1990, 1995): (157, 161),  # Pre-expansion
        range(1995, 2011): (185, 186),  # Standard era
        range(2011, 2020): (198, 209),  # 18 teams
        2020: (153, 163),  # COVID-affected
        range(2021, 2026): (189, 210)   # Modern era
    }
    
    expected = None
    for key, (min_exp, max_exp) in expected_ranges.items():
        if isinstance(key, range) and year in key:
            expected = (min_exp, max_exp)
            break
        elif isinstance(key, int) and year == key:
            expected = (min_exp, max_exp)
            break
    
    status = 'OK'
    if expected:
        if count < expected[0]:
            status = 'INCOMPLETE'
            issues.append(f'Expected {expected[0]}-{expected[1]}, got {count}')
        elif count > expected[1]:
            status = 'EXCESS'
            issues.append(f'Expected {expected[0]}-{expected[1]}, got {count}')
    
    return {
        'year': year,
        'count': count,
        'status': status if not issues else 'ISSUES',
        'issues': issues if issues else ['None']
    }

def main():
    engine = get_engine()
    session = get_session(engine)
    
    print('='*80)
    print('AFL DATA INTEGRITY REPORT')
    print('='*80)
    
    results = []
    for year in range(1990, 2026):
        result = analyze_season(session, year)
        results.append(result)
    
    # Print summary
    print(f'\n{"Year":<6} {"Matches":<10} {"Status":<12} {"Issues"}')
    print('-'*80)
    
    total_matches = 0
    problem_years = []
    
    for r in results:
        total_matches += r['count']
        issues_str = '; '.join(r['issues'][:2])  # Show first 2 issues
        if len(r['issues']) > 2:
            issues_str += f' (+{len(r["issues"])-2} more)'
        
        status_display = r['status']
        if r['status'] in ['ISSUES', 'INCOMPLETE', 'EXCESS']:
            problem_years.append(r['year'])
            status_display = f'⚠️  {r["status"]}'
        elif r['status'] == 'OK':
            status_display = '✓ OK'
        
        print(f'{r["year"]:<6} {r["count"]:<10} {status_display:<12} {issues_str}')
    
    print('-'*80)
    print(f'Total matches: {total_matches}')
    print(f'Years analyzed: {len(results)}')
    print(f'Problem years: {len(problem_years)}')
    
    if problem_years:
        print(f'\nYears needing attention: {", ".join(map(str, problem_years))}')
    else:
        print('\n✓ All years look good!')

if __name__ == '__main__':
    main()
