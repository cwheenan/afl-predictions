"""Run all remaining data ingestion batches sequentially."""
import subprocess
import sys
from pathlib import Path

def run_batch(years, description):
    """Run batch ingestion for a group of years."""
    print(f'\n{"="*70}')
    print(f'BATCH: {description}')
    print(f'Years: {years}')
    print(f'{"="*70}\n')
    
    for year in years:
        cmd = [
            sys.executable,
            'scripts/ingest_season.py',
            '--year', str(year),
            '--rounds', '1-23',
            '--rate', '1.5',
            '--resume'
        ]
        
        print(f'\n>>> Starting {year}...')
        result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
        
        if result.returncode != 0:
            print(f'ERROR: Year {year} failed!')
            return False
        
        print(f'✓ {year} complete')
    
    return True

def main():
    batches = [
        ([2015], "Complete 2015"),
        ([2016, 2017, 2018, 2019], "2016-2019"),
        ([2020, 2021], "2020-2021"),
        ([2022], "Complete 2022"),
        ([2023, 2024], "2023-2024"),
        ([2025], "2025 (if available)")
    ]
    
    print('='*70)
    print('REMAINING DATA INGESTION')
    print('='*70)
    print(f'Total batches: {len(batches)}')
    print(f'Total years: {sum(len(b[0]) for b in batches)}')
    print(f'Estimated time: ~60 minutes')
    print('='*70)
    
    for years, desc in batches:
        success = run_batch(years, desc)
        if not success:
            print(f'\nStopped due to error in batch: {desc}')
            sys.exit(1)
    
    print('\n' + '='*70)
    print('ALL REMAINING DATA INGESTION COMPLETE!')
    print('='*70)

if __name__ == '__main__':
    main()
