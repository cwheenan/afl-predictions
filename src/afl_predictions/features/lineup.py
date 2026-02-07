"""Lineup feature utilities.

Small utilities to compute simple expected-presence probabilities and aggregate
team-level features for a match. These are intentionally lightweight and
interpretable for the early sanity-check pipeline.

Functions:
- player_presence_prob(session, player_id, lookback_matches=50)
- team_aggregated_stats_for_match(session, match_id)

These functions use `player_stats` historical naming info and canonical
stat columns to compute simple features useful for baseline models.
"""
from typing import Dict, Any, Iterable, Tuple
import math
import json

from sqlalchemy import func, or_

from afl_predictions.db import PlayerStats, Player, Match, MatchLineup, MatchOdds


def _parse_stats_json(sj: dict) -> Dict[str, float]:
    """Normalize messy stats_json keys into canonical stat names.

    The AFLTables cached tables often use verbose column headings like
    "Carlton Match Statistics [Season][Game by Game]" rather than
    canonical keys. We attempt fuzzy matching on the key text to extract
    numeric values for the canonical stat columns.
    """
    if not sj:
        return {}
    out = {}
    # canonical keys we care about
    canonical = ['goals', 'behinds', 'kicks', 'handballs', 'disposals', 'marks', 'tackles', 'hitouts', 'frees_for', 'frees_against']
    # prepare lowercase mapping
    for k, v in sj.items():
        if v is None:
            continue
        kl = k.lower()
        try:
            num = float(v)
        except Exception:
            # some values may be strings with commas
            try:
                num = float(str(v).replace(',', ''))
            except Exception:
                continue

        # map by substring matches
        if 'goal' in kl and 'behind' not in kl:
            out['goals'] = out.get('goals', 0.0) + num
        elif 'behind' in kl:
            out['behinds'] = out.get('behinds', 0.0) + num
        elif 'kick' in kl:
            out['kicks'] = out.get('kicks', 0.0) + num
        elif 'hand' in kl and 'handball' in kl or 'handball' in kl:
            out['handballs'] = out.get('handballs', 0.0) + num
        elif 'dispos' in kl:
            out['disposals'] = out.get('disposals', 0.0) + num
        elif 'mark' in kl:
            out['marks'] = out.get('marks', 0.0) + num
        elif 'tackle' in kl:
            out['tackles'] = out.get('tackles', 0.0) + num
        elif 'hitout' in kl:
            out['hitouts'] = out.get('hitouts', 0.0) + num
        elif 'free' in kl and 'against' in kl:
            out['frees_against'] = out.get('frees_against', 0.0) + num
        elif 'free' in kl and 'for' in kl:
            out['frees_for'] = out.get('frees_for', 0.0) + num
        # catch-all: if key exactly matches canonical
        elif kl in canonical:
            out[kl] = out.get(kl, 0.0) + num

    # ensure all canonical keys are present as numbers
    for c in canonical:
        out.setdefault(c, 0.0)
    return out


def player_presence_prob(session, player_id: int, lookback_matches: int = 50) -> float:
    """Estimate a player's probability to be named based on recent matches.

    Simple frequency: #named / #matches seen (limited to lookback_matches recent rows)
    Returns a float in [0.0, 1.0]. If no history, returns 0.5 (uninformative prior).
    """
    if player_id is None:
        return 0.5

    q = session.query(PlayerStats).filter(PlayerStats.player_id == player_id).order_by(PlayerStats.id.desc()).limit(lookback_matches)
    rows = q.all()
    total = len(rows)
    if total == 0:
        return 0.5
    named = sum(1 for r in rows if r.named)
    return named / total


def recency_weighted_presence(session, player_id: int, lookback_matches: int = 50, half_life: float = 10.0) -> float:
    """Return a recency-weighted presence probability in [0,1].

    Weighted sum: weights = 2^{-age/half_life} where age=0 for most recent.
    If no history, returns 0.5 as uninformative prior.
    """
    if player_id is None:
        return 0.5

    rows = session.query(PlayerStats).filter(PlayerStats.player_id == player_id).order_by(PlayerStats.id.desc()).limit(lookback_matches).all()
    if not rows:
        return 0.5

    total_w = 0.0
    weighted_named = 0.0
    for age, r in enumerate(rows):
        w = 2 ** (-(age / half_life))
        total_w += w
        if r.named:
            weighted_named += w

    if total_w == 0:
        return 0.5
    return float(weighted_named / total_w)


def expected_squad_probs(session, match_id: int) -> Dict[int, float]:
    """Return a dict mapping player_id -> expected presence probability for a match.

    Priority:
    - if MatchLineup.expected_probability is present, use it
    - else if MatchLineup row exists with is_named, use 1.0 for named, 0.5 otherwise
    - otherwise fall back to recency_weighted_presence
    """
    out = {}
    # try to use match_lineups if available
    mls = session.query(MatchLineup).filter(MatchLineup.match_id == match_id).all()
    if mls:
        for ml in mls:
            if ml.expected_probability is not None:
                out[ml.player_id] = float(ml.expected_probability)
            elif ml.is_named is not None:
                out[ml.player_id] = 1.0 if ml.is_named else 0.5
            else:
                out[ml.player_id] = recency_weighted_presence(session, ml.player_id)
        return out

    # fallback: infer named players from player_stats for this match
    rows = session.query(PlayerStats).filter(PlayerStats.match_id == match_id).all()
    for r in rows:
        pid = r.player_id
        if r.named is not None:
            out[pid] = 1.0 if r.named else 0.5
        else:
            out[pid] = recency_weighted_presence(session, pid)

    return out


def player_recent_stats(session, player_id: int, n: int = 5) -> Dict[str, float]:
    """Return simple recent averages for a player (last n appearances).

    Returns averages for: goals, disposals, kicks, marks, tackles. Missing values treated as 0.
    """
    rows = session.query(PlayerStats).filter(PlayerStats.player_id == player_id).order_by(PlayerStats.id.desc()).limit(n).all()
    if not rows:
        return {k: 0.0 for k in ('goals', 'disposals', 'kicks', 'marks', 'tackles')}
    sums = {'goals': 0.0, 'disposals': 0.0, 'kicks': 0.0, 'marks': 0.0, 'tackles': 0.0}
    count = 0
    for r in rows:
        count += 1
        for k in sums.keys():
            v = getattr(r, k, None)
            if v is None:
                # try stats_json fallback with fuzzy key parsing
                try:
                    sj = json.loads(r.stats_json) if r.stats_json else {}
                    norm = _parse_stats_json(sj)
                    v = float(norm.get(k) or 0)
                except Exception:
                    v = 0.0
            sums[k] += float(v or 0.0)

    return {k: (sums[k] / count if count else 0.0) for k in sums}


def assemble_player_features(session, match_id: int, lookback_matches: int = 50) -> Dict[int, Dict[str, float]]:
    """Assemble per-player feature dicts for all players associated with a match.

    Features include:
    - presence_prob (recency-weighted or match_lineup expected)
    - avg_percent_played (from player_stats row if present)
    - recent_goals, recent_disposals, recent_kicks, recent_marks, recent_tackles
    - is_named (from MatchLineup if available)
    """
    out = {}
    probs = expected_squad_probs(session, match_id)
    # gather players: from match_lineups if present else from player_stats
    players: Iterable[Tuple[int, Any]] = []
    mls = session.query(MatchLineup).filter(MatchLineup.match_id == match_id).all()
    if mls:
        players = [(ml.player_id, ml) for ml in mls]
    else:
        rows = session.query(PlayerStats).filter(PlayerStats.match_id == match_id).all()
        players = [(r.player_id, r) for r in rows]

    for pid, obj in players:
        prob = probs.get(pid, recency_weighted_presence(session, pid, lookback_matches=lookback_matches))
        # try to read avg percent_played from the player_stats row for this match
        avg_percent = None
        if isinstance(obj, MatchLineup):
            # look up player_stats for this match/player
            ps = session.query(PlayerStats).filter(PlayerStats.match_id == match_id, PlayerStats.player_id == pid).first()
            avg_percent = float(ps.percent_played) if ps and ps.percent_played is not None else None
            is_named = bool(obj.is_named) if obj.is_named is not None else None
        else:
            ps = obj
            avg_percent = float(ps.percent_played) if ps and ps.percent_played is not None else None
            is_named = bool(ps.named) if ps and ps.named is not None else None

        recent = player_recent_stats(session, pid, n=5)
        feats = {
            'presence_prob': float(prob),
            'avg_percent_played': float(avg_percent) if avg_percent is not None else 0.0,
            'recent_goals': float(recent.get('goals', 0.0)),
            'recent_disposals': float(recent.get('disposals', 0.0)),
            'recent_kicks': float(recent.get('kicks', 0.0)),
            'recent_marks': float(recent.get('marks', 0.0)),
            'recent_tackles': float(recent.get('tackles', 0.0)),
            'is_named': 1.0 if is_named else 0.0,
        }
        out[pid] = feats

    return out


def team_weighted_features(session, match_id: int) -> Dict[str, float]:
    """Compute simple team-level features weighted by presence probability.

    Returns a dict with features for home and away team and their differences.
    """
    m = session.get(Match, match_id)
    if m is None:
        raise ValueError('match not found')

    per_player = assemble_player_features(session, match_id)

    home_players = {}
    away_players = {}
    # need player->team mapping from player_stats for this match
    rows = session.query(PlayerStats).filter(PlayerStats.match_id == match_id).all()
    pid_to_team = {r.player_id: r.team for r in rows if r.player_id is not None}

    for pid, feats in per_player.items():
        team = pid_to_team.get(pid)
        if team == m.home_team:
            home_players[pid] = feats
        elif team == m.away_team:
            away_players[pid] = feats

    def agg(players: Dict[int, Dict[str, float]]):
        # weighted sums by presence_prob for recent stats
        keys = ['recent_goals', 'recent_disposals', 'recent_kicks', 'recent_marks', 'recent_tackles']
        res = {f'wt_{k}': 0.0 for k in keys}
        total_w = 0.0
        for pid, f in players.items():
            w = float(f.get('presence_prob', 0.5))
            total_w += w
            for k in keys:
                res[f'wt_{k}'] += w * float(f.get(k, 0.0))
        # normalize
        if total_w > 0:
            for k in keys:
                res[f'wt_{k}'] = res[f'wt_{k}'] / total_w
        return res, len(players)

    h_agg, h_n = agg(home_players)
    a_agg, a_n = agg(away_players)

    fv = {}
    # include counts
    fv['home_player_count'] = h_n
    fv['away_player_count'] = a_n
    # include weighted stats and diffs
    for k in h_agg.keys():
        fv[f'home_{k}'] = h_agg[k]
        fv[f'away_{k}'] = a_agg[k]
        fv[f'diff_{k}'] = h_agg[k] - a_agg[k]

    return fv


def match_level_vector(session, match_id: int) -> Tuple[list, list]:
    """Return a fixed-length feature vector and corresponding names for the match.

    Uses `team_weighted_features` to produce a compact, fixed-size vector suitable
    for quick modeling. Returns (vector, feature_names).
    """
    fv = team_weighted_features(session, match_id)
    names = sorted(fv.keys())
    vec = [float(fv[n]) for n in names]
    return vec, names


def team_aggregated_stats_for_match(session, match_id: int) -> Dict[str, Dict[str, Any]]:
    """Return aggregated stats per team for the given match.

    Aggregates include sums of canonical stat columns and average percent_played
    among named players. Returns a dict keyed by team name with simple stats.
    """
    # canonical stat columns we care about
    cols = ['goals', 'behinds', 'kicks', 'handballs', 'disposals', 'marks', 'tackles', 'hitouts', 'frees_for', 'frees_against']

    teams = {}
    # fetch all player_stats for the match
    rows = session.query(PlayerStats).filter(PlayerStats.match_id == match_id).all()
    for r in rows:
        team = r.team or 'UNKNOWN'
        t = teams.setdefault(team, {c: 0 for c in cols})
        t.setdefault('players', 0)
        t.setdefault('avg_percent_played', [])
        t['players'] += 1
        try:
            sj = json.loads(r.stats_json) if r.stats_json else {}
        except Exception:
            sj = {}
        # normalize stats_json to canonical keys and then aggregate
        norm = _parse_stats_json(sj)
        for c in cols:
            val = getattr(r, c, None)
            if val is None:
                try:
                    v = norm.get(c, 0.0)
                    val = int(v) if v is not None else 0
                except Exception:
                    val = 0
            t[c] += val or 0

        if r.percent_played is not None:
            t['avg_percent_played'].append(float(r.percent_played))

    # finalize avg_percent_played
    for team, t in teams.items():
        arr = t.get('avg_percent_played', [])
        t['avg_percent_played'] = (sum(arr) / len(arr)) if arr else 0.0

    return teams


def team_historical_aggregates(session, team_name: str, before_match_id: int, n: int = 5) -> Dict[str, Any]:
    """Compute average per-match aggregated canonical stats for the team's last n matches before a given match.

    Returns a dict with the same keys as `team_aggregated_stats_for_match` for a single match
    but averaged across the last `n` matches. If no prior matches are found, returns
    zeroed stats and avg_percent_played 0.0.
    """
    cols = ['goals', 'behinds', 'kicks', 'handballs', 'disposals', 'marks', 'tackles', 'hitouts', 'frees_for', 'frees_against']

    if not team_name:
        return {c: 0.0 for c in cols} | {'players': 0, 'avg_percent_played': 0.0}

    # find prior match ids where the team participated and which have scores
    mid_rows = (
        session.query(Match.match_id)
        .filter(
            or_(Match.home_team == team_name, Match.away_team == team_name),
            Match.match_id < before_match_id,
            Match.home_score != None,
            Match.away_score != None,
        )
        .order_by(Match.match_id.desc())
        .limit(n)
        .all()
    )
    match_ids = [r[0] for r in mid_rows]
    if not match_ids:
        return {c: 0.0 for c in cols} | {'players': 0, 'avg_percent_played': 0.0}

    per_match_totals = []
    per_match_players = []
    per_match_avg_percent = []
    for mid in match_ids:
        rows = session.query(PlayerStats).filter(PlayerStats.match_id == mid, PlayerStats.team == team_name).all()
        if not rows:
            # treat as zero match
            per_match_totals.append({c: 0.0 for c in cols})
            per_match_players.append(0)
            per_match_avg_percent.append(0.0)
            continue

        t = {c: 0.0 for c in cols}
        players = 0
        percents = []
        for r in rows:
            players += 1
            try:
                sj = json.loads(r.stats_json) if r.stats_json else {}
            except Exception:
                sj = {}
            norm = _parse_stats_json(sj)
            for c in cols:
                val = getattr(r, c, None)
                if val is None:
                    try:
                        v = norm.get(c, 0.0)
                        val = float(v or 0.0)
                    except Exception:
                        val = 0.0
                t[c] += float(val or 0.0)
            if r.percent_played is not None:
                percents.append(float(r.percent_played))

        per_match_totals.append(t)
        per_match_players.append(players)
        per_match_avg_percent.append((sum(percents) / len(percents)) if percents else 0.0)

    # average across matches
    avg_tot = {c: 0.0 for c in cols}
    for t in per_match_totals:
        for c in cols:
            avg_tot[c] += t.get(c, 0.0)
    for c in cols:
        avg_tot[c] = avg_tot[c] / len(per_match_totals)

    avg_players = sum(per_match_players) / len(per_match_players)
    avg_percent_played = sum(per_match_avg_percent) / len(per_match_avg_percent)

    out = {c: avg_tot[c] for c in cols}
    out['players'] = int(round(avg_players))
    out['avg_percent_played'] = float(avg_percent_played)
    return out


def team_recent_margin(session, team_name: str, before_match_id: int, n: int = 5) -> float:
    """Compute the average margin (team_score - opponent_score) for the team's last n matches before a given match id.

    Uses Match.id ordering as a proxy for chronology. If no prior matches with scores are found, returns 0.0.
    """
    if not team_name:
        return 0.0

    q = (
        session.query(Match)
        .filter(
            or_(Match.home_team == team_name, Match.away_team == team_name),
                Match.match_id < before_match_id,
            Match.home_score != None,
            Match.away_score != None,
        )
    .order_by(Match.match_id.desc())
        .limit(n)
    )
    rows = q.all()
    if not rows:
        return 0.0

    margins = []
    for m in rows:
        try:
            hs = float(m.home_score)
            as_ = float(m.away_score)
        except Exception:
            continue
        if m.home_team == team_name:
            margins.append(hs - as_)
        elif m.away_team == team_name:
            margins.append(as_ - hs)

    if not margins:
        return 0.0
    return float(sum(margins) / len(margins))


def team_win_percentage(session, team_name: str, before_match_id: int, n: int = 10) -> float:
    """Compute the win percentage for the team's last n matches before a given match id.
    
    Returns value between 0.0 and 1.0. Returns 0.5 if no prior matches found.
    """
    if not team_name:
        return 0.5
    
    q = (
        session.query(Match)
        .filter(
            or_(Match.home_team == team_name, Match.away_team == team_name),
            Match.match_id < before_match_id,
            Match.home_score != None,
            Match.away_score != None,
        )
        .order_by(Match.match_id.desc())
        .limit(n)
    )
    rows = q.all()
    if not rows:
        return 0.5
    
    wins = 0
    for m in rows:
        try:
            hs = float(m.home_score)
            as_ = float(m.away_score)
            
            if m.home_team == team_name and hs > as_:
                wins += 1
            elif m.away_team == team_name and as_ > hs:
                wins += 1
        except Exception:
            continue
    
    return float(wins) / len(rows)


def head_to_head_record(session, home_team: str, away_team: str, before_match_id: int, n: int = 10) -> float:
    """Compute win percentage for home_team against away_team in their last n meetings.
    
    Returns value between 0.0 and 1.0. Returns 0.5 if no prior meetings found.
    """
    if not home_team or not away_team:
        return 0.5
    
    q = (
        session.query(Match)
        .filter(
            or_(
                (Match.home_team == home_team) & (Match.away_team == away_team),
                (Match.home_team == away_team) & (Match.away_team == home_team)
            ),
            Match.match_id < before_match_id,
            Match.home_score != None,
            Match.away_score != None,
        )
        .order_by(Match.match_id.desc())
        .limit(n)
    )
    rows = q.all()
    if not rows:
        return 0.5
    
    wins = 0
    for m in rows:
        try:
            hs = float(m.home_score)
            as_ = float(m.away_score)
            
            # Check if home_team won
            if m.home_team == home_team and hs > as_:
                wins += 1
            elif m.away_team == home_team and as_ > hs:
                wins += 1
        except Exception:
            continue
    
    return float(wins) / len(rows)


def team_venue_performance(session, team_name: str, venue: str, before_match_id: int, n: int = 10) -> float:
    """Compute win percentage for team at a specific venue in their last n matches there.
    
    Returns value between 0.0 and 1.0. Returns 0.5 if no prior matches at venue found.
    """
    if not team_name or not venue:
        return 0.5
    
    q = (
        session.query(Match)
        .filter(
            or_(Match.home_team == team_name, Match.away_team == team_name),
            Match.venue == venue,
            Match.match_id < before_match_id,
            Match.home_score != None,
            Match.away_score != None,
        )
        .order_by(Match.match_id.desc())
        .limit(n)
    )
    rows = q.all()
    if not rows:
        return 0.5
    
    wins = 0
    for m in rows:
        try:
            hs = float(m.home_score)
            as_ = float(m.away_score)
            
            if m.home_team == team_name and hs > as_:
                wins += 1
            elif m.away_team == team_name and as_ > hs:
                wins += 1
        except Exception:
            continue
    
    return float(wins) / len(rows)


def get_odds_features(session, match_id: int) -> Dict[str, float]:
    """Extract betting odds features for a match.
    
    Returns implied probabilities and odds ratios from betting markets.
    If no odds available, returns neutral values (0.5 probability).
    """
    # Query for odds data
    odds_records = session.query(MatchOdds).filter(
        MatchOdds.match_id == match_id
    ).all()
    
    if not odds_records:
        # No odds data available - return neutral values
        return {
            'odds_home_win_prob': 0.5,
            'odds_away_win_prob': 0.5,
            'odds_home_favored': 0.0,  # 0 = neutral
            'odds_spread': 0.0,
            'odds_confidence': 0.0,  # 0 = no odds data
        }
    
    # Use average across all bookmakers/sources
    home_probs = []
    away_probs = []
    line_spreads = []
    
    for odds in odds_records:
        if odds.home_win_odds and odds.away_win_odds:
            # Convert decimal odds to implied probability
            home_prob = 1.0 / odds.home_win_odds
            away_prob = 1.0 / odds.away_win_odds
            
            # Remove bookmaker margin (normalize to sum to 1.0)
            total = home_prob + away_prob
            if total > 0:
                home_prob = home_prob / total
                away_prob = away_prob / total
                
                home_probs.append(home_prob)
                away_probs.append(away_prob)
        
        if odds.line_spread is not None:
            line_spreads.append(odds.line_spread)
    
    if not home_probs:
        # Odds exist but couldn't extract probabilities
        return {
            'odds_home_win_prob': 0.5,
            'odds_away_win_prob': 0.5,
            'odds_home_favored': 0.0,
            'odds_spread': 0.0,
            'odds_confidence': 0.0,
        }
    
    # Average probabilities across bookmakers
    avg_home_prob = sum(home_probs) / len(home_probs)
    avg_away_prob = sum(away_probs) / len(away_probs)
    avg_spread = sum(line_spreads) / len(line_spreads) if line_spreads else 0.0
    
    # Odds confidence: how strong is the favorite?
    # Higher values = more lopsided odds (clearer favorite)
    confidence = abs(avg_home_prob - 0.5)
    
    # Home favored: +1 if home favored, -1 if away favored, 0 if even
    if avg_home_prob > 0.55:
        home_favored = 1.0
    elif avg_home_prob < 0.45:
        home_favored = -1.0
    else:
        home_favored = 0.0
    
    return {
        'odds_home_win_prob': float(avg_home_prob),
        'odds_away_win_prob': float(avg_away_prob),
        'odds_home_favored': float(home_favored),
        'odds_spread': float(avg_spread),
        'odds_confidence': float(confidence),
    }


def features_for_match(session, match_id: int) -> Dict[str, float]:
    """Build a flat feature vector for a match usable by a simple model.

    The vector includes differences (home - away) of aggregated stats and
    expected presence sums based on historical frequency.
    
    Enhanced features include:
    - Historical aggregates (last 5 matches)
    - Recent form (win percentage)
    - Head-to-head history
    - Venue-specific performance
    - Scoring efficiency metrics
    """
    m = session.get(Match, match_id)
    if m is None:
        raise ValueError('match not found')

    # Use historical aggregates (no leakage): compute average per-match stats
    # from the last N matches before this match for each team.
    home = team_historical_aggregates(session, m.home_team, match_id, n=5)
    away = team_historical_aggregates(session, m.away_team, match_id, n=5)

    def g(t, k):
        return (t.get(k, 0) if t else 0)

    fv = {}
    # stat diffs
    for c in ['goals', 'behind', 'kicks', 'handballs', 'disposals', 'marks', 'tackles', 'hitouts', 'frees_for', 'frees_against']:
        # map behind->behinds
        k = 'behinds' if c == 'behind' else c
        hv = g(home, k)
        av = g(away, k)
        fv[f'diff_{k}'] = hv - av

    fv['diff_avg_percent_played'] = float(home.get('avg_percent_played', 0.0) - away.get('avg_percent_played', 0.0))
    fv['home_players'] = int(home.get('players', 0))
    fv['away_players'] = int(away.get('players', 0))

    # recent form: average margin in last n matches for each team (home - away)
    try:
        home_margin = team_recent_margin(session, m.home_team, match_id, n=5)
        away_margin = team_recent_margin(session, m.away_team, match_id, n=5)
    except Exception:
        home_margin = 0.0
        away_margin = 0.0

    fv['home_recent_margin'] = float(home_margin)
    fv['away_recent_margin'] = float(away_margin)
    fv['diff_recent_margin'] = float(home_margin - away_margin)
    
    # Enhanced features: recent form (win percentage)
    try:
        home_win_pct = team_win_percentage(session, m.home_team, match_id, n=10)
        away_win_pct = team_win_percentage(session, m.away_team, match_id, n=10)
        fv['home_win_pct_10'] = float(home_win_pct)
        fv['away_win_pct_10'] = float(away_win_pct)
        fv['diff_win_pct_10'] = float(home_win_pct - away_win_pct)
    except Exception:
        fv['home_win_pct_10'] = 0.5
        fv['away_win_pct_10'] = 0.5
        fv['diff_win_pct_10'] = 0.0
    
    # Head-to-head history
    try:
        h2h_home_win_pct = head_to_head_record(session, m.home_team, m.away_team, match_id, n=10)
        fv['h2h_home_win_pct'] = float(h2h_home_win_pct)
    except Exception:
        fv['h2h_home_win_pct'] = 0.5
    
    # Venue-specific performance (home team at this venue)
    try:
        venue_win_pct = team_venue_performance(session, m.home_team, m.venue, match_id, n=10)
        fv['home_venue_win_pct'] = float(venue_win_pct)
    except Exception:
        fv['home_venue_win_pct'] = 0.5
    
    # Scoring efficiency (goals per inside 50, conversion rate approximation)
    try:
        home_goals = g(home, 'goals')
        away_goals = g(away, 'goals')
        home_behinds = g(home, 'behinds')
        away_behinds = g(away, 'behinds')
        
        # Conversion rate: goals / (goals + behinds)
        home_conv = home_goals / (home_goals + home_behinds) if (home_goals + home_behinds) > 0 else 0.5
        away_conv = away_goals / (away_goals + away_behinds) if (away_goals + away_behinds) > 0 else 0.5
        
        fv['home_conversion_rate'] = float(home_conv)
        fv['away_conversion_rate'] = float(away_conv)
        fv['diff_conversion_rate'] = float(home_conv - away_conv)
    except Exception:
        fv['home_conversion_rate'] = 0.5
        fv['away_conversion_rate'] = 0.5
        fv['diff_conversion_rate'] = 0.0
    
    # Longer term form (last 20 matches margin)
    try:
        home_margin_20 = team_recent_margin(session, m.home_team, match_id, n=20)
        away_margin_20 = team_recent_margin(session, m.away_team, match_id, n=20)
        fv['home_margin_20'] = float(home_margin_20)
        fv['away_margin_20'] = float(away_margin_20)
        fv['diff_margin_20'] = float(home_margin_20 - away_margin_20)
    except Exception:
        fv['home_margin_20'] = 0.0
        fv['away_margin_20'] = 0.0
        fv['diff_margin_20'] = 0.0
    
    # Betting odds features (if available)
    try:
        odds_features = get_odds_features(session, match_id)
        fv.update(odds_features)
    except Exception:
        # No odds data or error - use neutral values
        fv['odds_home_win_prob'] = 0.5
        fv['odds_away_win_prob'] = 0.5
        fv['odds_home_favored'] = 0.0
        fv['odds_spread'] = 0.0
        fv['odds_confidence'] = 0.0

    return fv
