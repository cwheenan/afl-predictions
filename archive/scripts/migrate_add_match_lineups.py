"""Migration to create `match_lineups` table and backfill from existing player_stats.

This script is idempotent: it will create the table if missing and insert rows for any
`player_stats` -> `match_lineups` mappings that don't already exist.

Usage: run from repo root with the repo's Python environment active:

    python scripts/migrate_add_match_lineups.py

"""
from pathlib import Path
import json
import sys

from afl_predictions import config
from afl_predictions.db import init_db, get_session, get_engine, PlayerStats, MatchLineup


def ensure_tables(db_url=None):
    engine = get_engine(db_url)
    # Importing models into metadata already done in db; create_all will create new tables
    from afl_predictions.db import Base

    Base.metadata.create_all(engine)
    return engine


def backfill_match_lineups(session):
    """Read all player_stats rows and ensure corresponding match_lineups rows exist.

    Heuristics:
    - is_named: use `named` column if set; otherwise True when stats_json exists and player_id present.
    - is_starting: True when percent_played == 100.0
    - position_role: try to extract from stats_json keys 'pos'|'position'|'role'.
    """
    q = session.query(PlayerStats)
    created = 0
    skipped = 0
    for ps in q.yield_per(100):
        if ps.match_id is None or ps.player_id is None:
            skipped += 1
            continue
        exists = session.query(MatchLineup).filter_by(match_id=ps.match_id, player_id=ps.player_id).first()
        if exists:
            skipped += 1
            continue

        # determine flags
        is_named = bool(ps.named) if ps.named is not None else bool(ps.stats_json)
        is_starting = (ps.percent_played == 100.0) if ps.percent_played is not None else False
        position_role = None
        try:
            sj = json.loads(ps.stats_json) if ps.stats_json else {}
            for k in ('pos', 'position', 'role'):
                if isinstance(sj, dict) and sj.get(k):
                    position_role = sj.get(k)
                    break
        except Exception:
            position_role = None

        ml = MatchLineup(
            match_id=ps.match_id,
            player_id=ps.player_id,
            is_named=is_named,
            is_starting=is_starting,
            position_role=position_role,
            expected_probability=None,
        )
        session.add(ml)
        created += 1

        # flush periodically to avoid long transactions
        if created % 500 == 0:
            session.commit()

    session.commit()
    return created, skipped


def main():
    engine = ensure_tables()
    session = get_session(engine)
    created, skipped = backfill_match_lineups(session)
    print(f"match_lineups backfill: created={created} skipped={skipped}")


if __name__ == '__main__':
    main()
