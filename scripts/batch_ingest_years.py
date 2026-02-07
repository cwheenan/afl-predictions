"""Batch ingest multiple years sequentially."""
import subprocess
import sys
from pathlib import Path

def ingest_year(year, rate=1.5):
    """Run ingest_season.py for a single year."""
    cmd = [
        sys.executable,
        'scripts/ingest_season.py',
        '--year', str(year),
        '--rounds', '1-23',
        '--rate', str(rate),
        '--resume'
    ]
    print(f'\n{"="*60}')
    print(f'Starting year {year}...')
    print(f'{"="*60}\n')
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    
    if result.returncode != 0:
        print(f'ERROR: Year {year} failed with exit code {result.returncode}')
        return False
    
    print(f'\n✓ Year {year} complete\n')
    return True

def main():
    years = [2011, 2012, 2013, 2014]
    
    print(f'Batch ingesting years: {years}')
    print(f'Estimated time: ~{len(years) * 5} minutes')
    print(f'Rate limit: 1.5 seconds between requests\n')
    
    for year in years:
        success = ingest_year(year)
        if not success:
            print(f'Stopping due to error with year {year}')
            sys.exit(1)
    
    print('\n' + '='*60)
    print('All years completed successfully!')
    print('='*60)

if __name__ == '__main__':
    main()
