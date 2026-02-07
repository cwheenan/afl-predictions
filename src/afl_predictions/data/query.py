"""Query helpers to read player stats from the processed DB.

These helpers assume you've seeded and parsed cached pages into the project's
database (default `config.DB_URL`, typically `data/processed/afl.db`). They do
not hit any remote servers.
"""
from typing import Optional, Dict, Any
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from afl_predictions import config
from afl_predictions.db import get_engine, get_session, Player, PlayerStats, Match


def get_player_stats(name: str, season: Optional[int] = None, round: Optional[str] = None, db_url: Optional[str] = None):
    """Return a list of player stat records (dict) matching the query.

    Each returned dict contains: match_id, season, round, date, team, stats (dict)
    """
    engine = get_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    q = session.query(Player, PlayerStats, Match).join(PlayerStats, Player.player_id == PlayerStats.player_id).join(Match, PlayerStats.match_id == Match.match_id)
    q = q.filter(Player.name.ilike(f"%{name}%"))
    if season is not None:
        q = q.filter(Match.season == season)
    if round is not None:
        q = q.filter(Match.round == str(round))

    results = []
    for player, pst, match in q:
        stats = {}
        try:
            stats = json.loads(pst.stats_json) if pst.stats_json else {}
        except Exception:
            # fallback: leave raw string
            stats = pst.stats_json

        results.append({
            'match_id': match.match_id,
            'season': match.season,
            'round': match.round,
            'date': match.date,
            'team': pst.team,
            'stats': stats,
        })

    session.close()
    return results


def find_goals_for(name: str, season: int, round: str, db_url: Optional[str] = None) -> Optional[int]:
    """Convenience helper: return the goals (int) for `name` in given season/round.

    Checks common keys ('GL', 'Goals') in the stats dict. Returns None if not found.
    """
    rows = get_player_stats(name, season=season, round=round, db_url=db_url)
    for r in rows:
        stats = r.get('stats') or {}
        # common keys
        for k in ('GL', 'Goals', 'gl', 'goals'):
            if k in stats and isinstance(stats[k], int):
                return stats[k]
            # sometimes stored as string
            if k in stats and isinstance(stats[k], str) and stats[k].isdigit():
                return int(stats[k])
    return None


__all__ = ['get_player_stats', 'find_goals_for']
