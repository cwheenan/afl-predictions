from afl_predictions.data import load_data
from afl_predictions.db import get_engine, get_session, Match, Player, PlayerStats
from afl_predictions.data import parse_match
import json


def _pick_stat(stats, keys):
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


def _pick_percent(stats):
    for k, v in stats.items():
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


def _pick_subs(stats):
    s_on = False
    s_off = False
    for k, v in stats.items():
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
        if isinstance(v, str):
            if '↑' in v or '\u2191' in v:
                s_on = True
            if '↓' in v or '\u2193' in v:
                s_off = True
    return s_on, s_off


def main():
    cache_dir = 'data/raw/cache'
    df = load_data.list_cached_matches(cache_dir)
    df2015 = df[df['url'].str.contains('/2015/')]
    tokens = df2015['token'].tolist()
    print('parsing tokens:', len(tokens))
    engine = get_engine()
    session = get_session(engine)
    for t in tokens:
        try:
            meta, players = parse_match.parse_match_from_cache(cache_dir, t)
            token_val = meta.get('token') or t
            existing = session.query(Match).filter_by(token=token_val).first()
            if existing:
                print('match exists, skipping insert', token_val)
                continue
            m = Match(token=token_val)
            try:
                if meta.get('season'):
                    m.season = int(meta.get('season'))
            except Exception:
                pass
            try:
                if meta.get('round'):
                    m.round = str(meta.get('round'))
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
            session.flush()

            added = 0
            for p in players:
                name = p.get('name')
                team = p.get('team')
                stats = p.get('stats') or {}

                player = session.query(Player).filter_by(name=name).first()
                if player is None:
                    player = Player(name=name)
                    session.add(player)
                    session.flush()

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
                    goals=_pick_stat(stats, ['GL', 'Goals', 'G', 'goals', 'gl']),
                    behinds=_pick_stat(stats, ['B', 'BH', 'Behinds', 'behinds', 'b']),
                    kicks=_pick_stat(stats, ['KI', 'K', 'Kicks', 'kicks', 'ki']),
                    handballs=_pick_stat(stats, ['HB', 'H', 'Handballs', 'handballs', 'hb']),
                    disposals=_pick_stat(stats, ['D', 'DI', 'Disp', 'Disposals', 'disposals', 'd']),
                    marks=_pick_stat(stats, ['MK', 'M', 'Marks', 'marks', 'mk']),
                    tackles=_pick_stat(stats, ['T', 'TK', 'TA', 'Tackles', 'tackles', 'tk']),
                    hitouts=_pick_stat(stats, ['HO', 'HitOuts', 'hitouts', 'ho']),
                    frees_for=_pick_stat(stats, ['FF', 'Ff', 'Frees For', 'frees_for', 'ff']),
                    frees_against=_pick_stat(stats, ['FA', 'Frees Against', 'frees_against', 'fa']),
                )
                session.add(ps)
                added += 1

            session.commit()
            print(f'Inserted match {token_val} with {added} player stats')
        except Exception as e:
            print('failed parse', t, e)


if __name__ == '__main__':
    main()
