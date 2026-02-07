"""Cross-platform runner for common pipeline tasks.

This script duplicates the convenience of the PowerShell runner but can be
invoked from any system with Python available. It calls the existing CLI scripts
that live under `scripts/`.

Examples:
    python scripts/run_pipeline.py --step init-env
    python scripts/run_pipeline.py --step init-db seed-db make-manifest
"""
import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd):
    print('->', ' '.join(cmd))
    res = subprocess.run(cmd, check=False)
    if res.returncode != 0:
        raise SystemExit(f'Command failed: {cmd}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--step', nargs='+', required=True, help='Steps to run (init-env init-db seed-db make-manifest crawl verify-cache)')
    p.add_argument('--cache-dir', default='data/raw/cache')
    p.add_argument('--seeds', default='data/raw/seeds.txt')
    p.add_argument('--master-list', default='data/raw/all_urls.txt')
    p.add_argument('--rate', type=int, default=3)
    args = p.parse_args()

    venv_py = Path('.venv') / ('Scripts' if sys.platform.startswith('win') else 'bin') / ('python.exe' if sys.platform.startswith('win') else 'python')

    for s in args.step:
        if s == 'init-env':
            if not Path('.venv').exists():
                run([sys.executable, '-m', 'venv', '.venv'])
            run([str(venv_py), '-m', 'pip', 'install', '--upgrade', 'pip'])
            run([str(venv_py), '-m', 'pip', 'install', '-r', 'requirements.txt'])
        elif s == 'init-db':
            run([str(venv_py), 'scripts/init_db.py'])
        elif s == 'seed-db':
            run([str(venv_py), 'scripts/seed_db.py', '--cache-dir', args.cache_dir])
        elif s == 'make-manifest':
            run([str(venv_py), 'scripts/make_manifest.py', '--out', 'data/processed/manifest.csv'])
        elif s == 'crawl':
            run([str(venv_py), 'scripts/crawl_afltables.py', args.seeds, '--cache-dir', args.cache_dir, '--master-list', args.master_list])
        elif s == 'verify-cache':
            run([str(venv_py), 'scripts/verify_cache.py', args.master_list, '--cache-dir', args.cache_dir, '--fetch-missing', '--rate', str(args.rate)])
        else:
            print('Unknown step:', s)


if __name__ == '__main__':
    main()
