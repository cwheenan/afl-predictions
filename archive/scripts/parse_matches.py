"""CLI to parse cached match pages and upsert into the local DB.

Usage (simple):
  python scripts/parse_matches.py --cache-dir data/raw/cache --tokens <token1> <token2>

Or sample from manifest:
  python scripts/parse_matches.py --manifest data/processed/manifest.csv --limit 10

This script is conservative: it will skip matches that already exist in the DB
by token. It writes minimal Match and PlayerStats rows so the parser can be
iterated later.
"""
import argparse
import json
from pathlib import Path

from afl_predictions.data import parse_match, load_data
from afl_predictions.db import get_engine, get_session, Match, Player, PlayerStats


def parse_and_upsert(cache_dir: str, token: str, session):
    meta, players = parse_match.parse_match_from_cache(cache_dir, token)
    token_val = meta.get('token') or token

    # If a match with this token exists, update missing metadata fields.
    existing = session.query(Match).filter_by(token=token_val).first()
    if existing:
        m = existing
        updated = False
        # populate fields if missing
        try:
            if getattr(m, 'season', None) is None and meta.get('season'):
                m.season = int(meta.get('season'))
                updated = True
        except Exception:
            pass
        try:
            if getattr(m, 'round', None) in (None, '') and meta.get('round'):
                m.round = str(meta.get('round'))
                try:
                    m.round_num = int(meta.get('round'))
                except Exception:
                    pass
                updated = True
        except Exception:
            pass
        # teams and scores
        try:
            teams = meta.get('teams') or meta.get('teams')
            scores = meta.get('scores')
            if teams and len(teams) >= 2:
                if not m.home_team:
                    m.home_team = teams[0]
                    updated = True
                if not m.away_team:
                    m.away_team = teams[1]
                    updated = True
            if scores and len(scores) >= 2:
                if not m.home_score:
                    m.home_score = int(scores[0])
                    updated = True
                if not m.away_score:
                    m.away_score = int(scores[1])
                    updated = True
        except Exception:
            pass
            # If title contains 'TeamA v TeamB', extract teams from title as fallback
            try:
                title = meta.get('title')
                if title and (not m.home_team or not m.away_team):
                    # pattern like 'AFL Tables - Geelong v Richmond - ...'
                    import re
                    mm = re.search(r"-\s*([^\-]+?)\s+v\s+([^\-]+?)\s+-", title)
                    if mm:
                        a = mm.group(1).strip()
                        b = mm.group(2).strip()
                        if not m.home_team:
                            m.home_team = a
                            updated = True
                        if not m.away_team:
                            m.away_team = b
                            updated = True
            except Exception:
                pass
        # date and venue
        try:
            if (not getattr(m, 'date', None)) and (meta.get('date_text') or meta.get('date')):
                m.date = meta.get('date') or meta.get('date_text')
                updated = True
            if (not getattr(m, 'venue', None)) and (meta.get('venue_text') or meta.get('venue')):
                m.venue = meta.get('venue') or meta.get('venue_text')
                updated = True
        except Exception:
            pass

        if updated:
            session.add(m)
            session.commit()
            print('Updated metadata for existing match', token_val)
        else:
            print('No metadata updates for existing match', token_val)
        # Attempt to update PlayerStats.team for existing player rows when
        # the parser now provides team names (idempotent update).
        for p in players:
            try:
                name = p.get('name')
                team = p.get('team')
                if not name or not team:
                    continue
                player = session.query(Player).filter_by(name=name).first()
                if not player:
                    continue
                ps = session.query(PlayerStats).filter_by(match_id=m.match_id, player_id=player.player_id).first()
                if ps and (ps.team is None or ps.team == ''):
                    ps.team = team
                    session.add(ps)
                    session.commit()
                    print(f'Updated team for player {name} in match {token_val} -> {team}')
            except Exception:
                session.rollback()
                continue
        # Heuristic: if many parsed players lack explicit team names but the
        # Match row has home/away team, assign players by splitting the list
        # in two and map first half -> home, second half -> away. This is a
        # pragmatic fallback for older pages where the parser couldn't detect
        # table-level team captions.
        try:
            missing = sum(1 for p in players if not p.get('team'))
            if missing > 0 and (missing / max(1, len(players))) > 0.5 and m.home_team and m.away_team:
                mid = len(players) // 2
                for i, p in enumerate(players):
                    name = p.get('name')
                    if not name:
                        continue
                    team_guess = m.home_team if i < mid else m.away_team
                    player = session.query(Player).filter_by(name=name).first()
                    if not player:
                        continue
                    ps = session.query(PlayerStats).filter_by(match_id=m.match_id, player_id=player.player_id).first()
                    if ps and (ps.team is None or ps.team == ''):
                        ps.team = team_guess
                        session.add(ps)
                session.commit()
                print(f'Applied heuristic team-split for match {token_val} -> {m.home_team}/{m.away_team}')
        except Exception:
            session.rollback()
            pass
        # avoid re-inserting player rows to prevent duplicates
        return 0

    m = Match(token=token_val)
    # populate metadata on new match
    try:
        if meta.get('season'):
            m.season = int(meta.get('season'))
    except Exception:
        pass
    try:
        if meta.get('round'):
            m.round = str(meta.get('round'))
            try:
                m.round_num = int(meta.get('round'))
            except Exception:
                pass
    except Exception:
        pass
    try:
        teams = meta.get('teams')
        scores = meta.get('scores')
        if teams and len(teams) >= 2:
            m.home_team = teams[0]
            m.away_team = teams[1]
        if scores and len(scores) >= 2:
            m.home_score = int(scores[0])
            m.away_score = int(scores[1])
    except Exception:
        pass
    # fallback: try to extract teams from title
    try:
        if (not m.home_team or not m.away_team) and meta.get('title'):
            import re
            mm = re.search(r"-\s*([^\-]+?)\s+v\s+([^\-]+?)\s+-", meta.get('title'))
            if mm:
                m.home_team = m.home_team or mm.group(1).strip()
                m.away_team = m.away_team or mm.group(2).strip()
    except Exception:
        pass
    try:
        if meta.get('date_text'):
            m.date = meta.get('date_text')
    except Exception:
        pass
    try:
        if meta.get('venue_text'):
            m.venue = meta.get('venue_text')
    except Exception:
        pass

    session.add(m)
    session.flush()  # obtain match_id

    added = 0
    seen_names = set()
    for p in players:
        # skip duplicate player entries (some pages have repeated rows);
        # use player name as the dedup key when available
        name_check = (p.get('name') or '').strip() if isinstance(p.get('name'), str) else p.get('name')
        if name_check:
            if name_check in seen_names:
                continue
            seen_names.add(name_check)
        name = p.get('name')
        team = p.get('team')
        stats = p.get('stats') or {}

        # find or create player
        player = session.query(Player).filter_by(name=name).first()
        if player is None:
            player = Player(name=name)
            session.add(player)
            session.flush()

        # derive canonical stat columns where possible
        def _pick_stat(keys):
            for k in keys:
                if k in stats and stats[k] is not None:
                    try:
                        v = stats[k]
                        if isinstance(v, str):
                            v = v.replace(',', '').strip()
                            if v.endswith('%') or v == '':
                                continue
                            v = float(v)
                        return int(v)
                    except Exception:
                        continue
            return None

        # determine percent_played and sub markers from stats dict
        def _pick_percent(st):
            """Return percent played as float (e.g., 43.0) when available, else None."""
            for k, v in st.items():
                try:
                    kn = str(k).lower()
                except Exception:
                    kn = ''
                if '%p' in kn or 'pct' in kn or 'percent' in kn:
                    if isinstance(v, str) and v.endswith('%'):
                        try:
                            return float(v.replace('%', '').strip())
                        except Exception:
                            continue
                    try:
                        return float(v)
                    except Exception:
                        continue
                if isinstance(v, str) and v.endswith('%'):
                    try:
                        return float(v.replace('%', '').strip())
                    except Exception:
                        continue
            return None

        def _pick_subs(st):
            s_on = False
            s_off = False
            for k, v in st.items():
                # inspect keys
                try:
                    kn = str(k)
                except Exception:
                    kn = ''
                if '\u2191' in kn or '\u2193' in kn or kn.strip().upper() == 'SU':
                    if isinstance(v, str):
                        if '↑' in v or '\u2191' in v or 'subbed on' in v.lower():
                            s_on = True
                        if '↓' in v or '\u2193' in v or 'subbed off' in v.lower():
                            s_off = True
                # inspect values
                if isinstance(v, str):
                    if '↑' in v or '\u2191' in v:
                        s_on = True
                    if '↓' in v or '\u2193' in v:
                        s_off = True
            return s_on, s_off

        pct = _pick_percent(stats)
        s_on, s_off = _pick_subs(stats)

        ps = PlayerStats(
            match_id=m.match_id,
            player_id=player.player_id,
            team=team,
            stats_json=json.dumps(stats),
            named=True,
            percent_played=pct,
            sub_on=bool(s_on),
            sub_off=bool(s_off),
            goals=_pick_stat(['GL', 'Goals', 'G', 'goals', 'gl']),
            behinds=_pick_stat(['B', 'BH', 'Behinds', 'behinds', 'b']),
            kicks=_pick_stat(['KI', 'K', 'Kicks', 'kicks', 'ki']),
            handballs=_pick_stat(['HB', 'H', 'Handballs', 'handballs', 'hb']),
            disposals=_pick_stat(['D', 'DI', 'Disp', 'Disposals', 'disposals', 'd']),
            marks=_pick_stat(['MK', 'M', 'Marks', 'marks', 'mk']),
            tackles=_pick_stat(['T', 'TK', 'TA', 'Tackles', 'tackles', 'tk']),
            hitouts=_pick_stat(['HO', 'HitOuts', 'hitouts', 'ho']),
            frees_for=_pick_stat(['FF', 'Ff', 'Frees For', 'frees_for', 'ff']),
            frees_against=_pick_stat(['FA', 'Frees Against', 'frees_against', 'fa']),
        )
        session.add(ps)
        added += 1

    session.commit()
    print(f'Inserted match {token_val} with {added} player stats')
    return added


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cache-dir', default='data/raw/cache')
    p.add_argument('--tokens', nargs='*')
    p.add_argument('--manifest')
    p.add_argument('--limit', type=int)
    args = p.parse_args()

    cache_dir = args.cache_dir
    engine = get_engine()
    session = get_session(engine)

    tokens = []
    if args.tokens:
        tokens = args.tokens
    elif args.manifest:
        import pandas as pd
        df = pd.read_csv(args.manifest)
        tokens = df['token'].tolist()
    else:
        print('No tokens or manifest provided; nothing to do.')
        return

    if args.limit:
        tokens = tokens[: args.limit]

    for t in tokens:
        try:
            parse_and_upsert(cache_dir, t, session)
        except Exception as e:
            print('Failed parsing', t, e)


if __name__ == '__main__':
    main()
