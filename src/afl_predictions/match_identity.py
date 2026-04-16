from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


def parse_match_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """Parse repo date strings into datetimes.

    Handles AFL Tables strings with optional local-time suffixes in parentheses
    and Squiggle ISO timestamps.
    """
    if not date_str:
        return None

    cleaned = date_str.split('(')[0].strip()
    formats = [
        '%a, %d-%b-%Y %I:%M %p',
        '%d-%b-%Y %I:%M %p',
        '%Y-%m-%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(cleaned.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def same_match_key(match) -> tuple[str, str, Optional[str]]:
    """Stable grouping key for duplicate rows representing the same fixture."""
    parsed = parse_match_datetime(getattr(match, 'date', None))
    date_key = parsed.date().isoformat() if parsed else None
    return (getattr(match, 'home_team', '') or '', getattr(match, 'away_team', '') or '', date_key)


def match_sort_key(match, target_dt: Optional[datetime] = None) -> tuple[int, int, int, int, int]:
    """Prefer richer rows when multiple rows represent the same match."""
    parsed = parse_match_datetime(getattr(match, 'date', None))
    day_distance = 999
    if target_dt and parsed:
        day_distance = abs((parsed.date() - target_dt.date()).days)

    has_token = 0 if getattr(match, 'token', None) else 1
    is_complete = 0 if getattr(match, 'home_score', None) is not None and getattr(match, 'away_score', None) is not None else 1
    has_venue = 0 if getattr(match, 'venue', None) else 1
    match_id = getattr(match, 'match_id', 10**9)
    return (day_distance, has_token, is_complete, has_venue, match_id)


def select_canonical_match(matches: Iterable, target_dt: Optional[datetime] = None):
    """Return the best row to represent a logical match.

    Identity is defined by home team, away team, and near-identical date.
    This deliberately ignores round labels because Opening Round / Round 0 can
    differ between data sources.
    """
    match_list = list(matches)
    if not match_list:
        return None
    return sorted(match_list, key=lambda match: match_sort_key(match, target_dt))[0]


def find_matching_matches(session, MatchModel, home_team: str, away_team: str, target_dt: Optional[datetime] = None, season: Optional[int] = None, day_tolerance: int = 3):
    """Find rows for the same logical game using teams plus date proximity."""
    query = session.query(MatchModel).filter(
        MatchModel.home_team == home_team,
        MatchModel.away_team == away_team,
    )
    if season is not None:
        query = query.filter(MatchModel.season == season)

    matches = query.all()
    if target_dt is None:
        return matches

    filtered = []
    for match in matches:
        parsed = parse_match_datetime(getattr(match, 'date', None))
        if parsed and abs((parsed.date() - target_dt.date()).days) <= day_tolerance:
            filtered.append(match)
    return filtered or matches


def canonical_round_for_group(matches: Iterable, target_dt: Optional[datetime] = None) -> Optional[str]:
    """Return the round value from the canonical row for a duplicate group."""
    canonical = select_canonical_match(matches, target_dt)
    if canonical is None:
        return None
    round_value = getattr(canonical, 'round', None)
    return str(round_value) if round_value not in (None, '') else None


def canonicalize_matches(matches: Iterable):
    """Deduplicate logical matches by team pairing and match date."""
    grouped_matches = {}
    for match in matches:
        grouped_matches.setdefault(same_match_key(match), []).append(match)

    canonical_matches = []
    for match_group in grouped_matches.values():
        canonical = select_canonical_match(match_group)
        if canonical is not None:
            canonical_matches.append(canonical)
    return canonical_matches


def detect_current_round(matches: Iterable, today: Optional[datetime] = None) -> Optional[int]:
    """Infer the current prediction round from canonical season matches.

    For an in-progress season, this returns the earliest round that still has an
    incomplete match scheduled on or after ``today``. If no future incomplete
    match is found, it falls back to the next round after the highest completed
    round.
    """
    today = today or datetime.now()
    canonical_matches = canonicalize_matches(matches)

    upcoming_rounds = []
    completed_rounds = []
    for match in canonical_matches:
        round_value = getattr(match, 'round', None)
        if round_value in (None, ''):
            continue
        try:
            round_num = int(round_value)
        except (TypeError, ValueError):
            continue

        parsed_dt = parse_match_datetime(getattr(match, 'date', None))
        is_complete = getattr(match, 'home_score', None) is not None and getattr(match, 'away_score', None) is not None

        if is_complete:
            completed_rounds.append(round_num)
            continue

        if parsed_dt is None or parsed_dt >= today:
            upcoming_rounds.append(round_num)

    if upcoming_rounds:
        return min(upcoming_rounds)
    if completed_rounds:
        return max(completed_rounds) + 1
    return None