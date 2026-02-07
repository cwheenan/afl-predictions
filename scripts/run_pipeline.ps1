<#
.SYNOPSIS
    Orchestrate common project tasks for the AFL predictions pipeline.

USAGE
    From repository root (Windows PowerShell):
    .\scripts\run_pipeline.ps1 -Step init-env
    .\scripts\run_pipeline.ps1 -Step seed-db

Available steps:
    init-env     - Create a virtualenv at .venv and install dependencies
    init-db      - Initialize the application database (creates tables)
    seed-db      - Seed pages into the DB from the cache index
    make-manifest- Create the manifest CSV from DB pages
    crawl        - Run the cautious crawler (requires seeds file)
    verify-cache - Verify master URL list and optionally fetch missing pages

Parameters can be combined in order, e.g. -Step init-env,init-db,seed-db
#>

param(
    [Parameter(Mandatory=$true)]
    [string[]]$Step,
    [string]$CacheDir = "data/raw/cache",
    [string]$SeedsFile = "data/raw/seeds.txt",
    [string]$MasterList = "data/raw/all_urls.txt",
    [int]$Rate = 3
)

function Run-Cmd([string]$cmd) {
    Write-Host "-> $cmd"
    & powershell -NoProfile -Command $cmd
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $cmd"
    }
}

foreach ($s in $Step) {
    switch ($s) {
        'init-env' {
            if (-Not (Test-Path -Path '.venv')) {
                Write-Host 'Creating virtual environment .venv'
                python -m venv .venv
            } else {
                Write-Host '.venv already exists'
            }
            Write-Host 'Installing requirements into .venv'
            .\.venv\Scripts\python.exe -m pip install --upgrade pip
            .\.venv\Scripts\python.exe -m pip install -r requirements.txt
        }
        'init-db' {
            Write-Host 'Initializing DB (creates data/processed/afl.db)'
            .\.venv\Scripts\python.exe scripts\init_db.py
        }
        'seed-db' {
            Write-Host 'Seeding DB from cache index'
            .\.venv\Scripts\python.exe scripts\seed_db.py --cache-dir $CacheDir
        }
        'make-manifest' {
            Write-Host 'Making manifest CSV'
            .\.venv\Scripts\python.exe scripts\make_manifest.py --out data/processed/manifest.csv
        }
        'crawl' {
            if (-Not (Test-Path -Path $SeedsFile)) {
                Write-Host "Seeds file not found: $SeedsFile"; break
            }
            Write-Host 'Running cautious crawler (may fetch pages)'
            .\.venv\Scripts\python.exe scripts\crawl_afltables.py $SeedsFile --cache-dir $CacheDir --master-list $MasterList
        }
        'verify-cache' {
            Write-Host 'Verifying master URL list and fetching missing entries (polite)'
            if (-Not (Test-Path -Path $MasterList)) { Write-Host "Master list not found: $MasterList"; break }
            .\.venv\Scripts\python.exe scripts\verify_cache.py $MasterList --cache-dir $CacheDir --fetch-missing --rate $Rate
        }
        Default {
            Write-Host "Unknown step: $s"
        }
    }
}
