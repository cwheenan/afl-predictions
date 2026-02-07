"""Database scaffold and helpers for afl_predictions using SQLAlchemy.

This module provides a minimal ORM mapping and helpers to create the DB and
seed the `pages` table from the existing cache index.

Design goals:
- Use SQLite by default (file at `data/processed/afl.db`) but allow overriding via
  `config.DB_URL` or an env var.
- Keep schema small initially: pages, matches, players, player_stats, umpires, teams
- Provide `init_db()` and `seed_pages_from_cache()` functions.
"""
from typing import Optional
from pathlib import Path
import json

from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    Float,
    String,
    Text,
    DateTime,
    ForeignKey,
    create_engine,
    Table,
    MetaData,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from afl_predictions import config
from afl_predictions.data import load_data

Base = declarative_base()


class Page(Base):
    __tablename__ = 'pages'
    token = Column(String, primary_key=True)
    url = Column(String, unique=True, index=True)
    page_type = Column(String, index=True)
    fetched_at = Column(Integer)
    html_path = Column(String)
    tables_json = Column(Text)


class Match(Base):
    __tablename__ = 'matches'
    match_id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String, ForeignKey('pages.token'))
    date = Column(String, index=True)
    season = Column(Integer, index=True)
    round = Column(String)
    venue = Column(String)
    home_team = Column(String, index=True)
    away_team = Column(String, index=True)
    home_score = Column(Integer)
    away_score = Column(Integer)


class Player(Base):
    __tablename__ = 'players'
    player_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, index=True)
    token = Column(String, index=True)


class PlayerStats(Base):
    __tablename__ = 'player_stats'
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey('matches.match_id'))
    player_id = Column(Integer, ForeignKey('players.player_id'))
    team = Column(String)
    stats_json = Column(Text)
    # explicit stat columns (nullable) for faster queries and normalization
    goals = Column(Integer)
    behinds = Column(Integer)
    kicks = Column(Integer)
    handballs = Column(Integer)
    disposals = Column(Integer)
    marks = Column(Integer)
    tackles = Column(Integer)
    hitouts = Column(Integer)
    frees_for = Column(Integer)
    frees_against = Column(Integer)
    # lineup / minute tracking
    named = Column(Boolean)
    percent_played = Column(Float)
    sub_on = Column(Boolean)
    sub_off = Column(Boolean)


class Umpire(Base):
    __tablename__ = 'umpires'
    umpire_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    token = Column(String, index=True)


class MatchOdds(Base):
    """Store betting odds for matches from various bookmakers."""
    __tablename__ = 'match_odds'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey('matches.match_id'), nullable=False, index=True)
    source = Column(String(50), nullable=False)  # 'tab', 'sportsbet', 'bet365', etc.
    
    # Head-to-head (H2H) odds
    home_win_odds = Column(Float)
    away_win_odds = Column(Float)
    
    # Line betting (handicap)
    home_line_odds = Column(Float)
    away_line_odds = Column(Float)
    line_spread = Column(Float)  # Negative = home favored
    
    # Totals (over/under)
    total_points = Column(Float)
    over_odds = Column(Float)
    under_odds = Column(Float)
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Relationships
    match = relationship('Match', backref='odds')


class MatchUmpire(Base):
    __tablename__ = 'match_umpires'
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey('matches.match_id'))
    umpire_id = Column(Integer, ForeignKey('umpires.umpire_id'))


class MatchLineup(Base):
    __tablename__ = 'match_lineups'
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey('matches.match_id'), index=True)
    player_id = Column(Integer, ForeignKey('players.player_id'), index=True)
    is_named = Column(Boolean)
    is_starting = Column(Boolean)
    position_role = Column(String, nullable=True)
    expected_probability = Column(Float, nullable=True)


def get_engine(db_url: Optional[str] = None):
    url = db_url or config.DB_URL
    # Ensure folder exists for sqlite file if path provided
    if url.startswith('sqlite:///'):
        fn = url.replace('sqlite:///', '')
        p = Path(fn)
        p.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, future=True)


def init_db(db_url: Optional[str] = None):
    """Create DB and tables."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine=None):
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def infer_page_type(url: str) -> str:
    # basic inference from URL path
    if '/afl/stats/games/' in url:
        return 'match'
    if '/afl/stats/umpires/' in url:
        return 'umpire'
    if '/afl/stats/players/' in url:
        return 'player'
    if '/afl/stats/teams/' in url:
        return 'team'
    return 'other'


def upsert_page(session, meta: dict):
    """Insert or update a Page row from meta dict (same shape as cache metadata)."""
    token = meta.get('token')
    url = meta.get('url')
    fetched_at = int(meta.get('fetched_at', 0))
    html_path = meta.get('html_path')
    tables = meta.get('tables', [])

    page_type = infer_page_type(url)
    try:
        page = session.get(Page, token)
        if page is None:
            page = Page(token=token, url=url, page_type=page_type, fetched_at=fetched_at, html_path=html_path, tables_json=json.dumps(tables))
            session.add(page)
        else:
            page.url = url
            page.page_type = page_type
            page.fetched_at = fetched_at
            page.html_path = html_path
            page.tables_json = json.dumps(tables)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        raise


def seed_pages_from_cache(cache_dir: Optional[str] = None, db_url: Optional[str] = None, limit: Optional[int] = None):
    """Read cache index and populate pages table. Returns number inserted."""
    engine = init_db(db_url)
    session = get_session(engine)
    cache_dir = cache_dir or str(config.DEFAULT_CACHE_DIR)
    df = load_data.list_cached_matches(cache_dir)
    if df.empty:
        return 0
    count = 0
    for idx, row in df.iterrows():
        meta = {
            'token': row['token'],
            'url': row['url'],
            'fetched_at': int(row['fetched_at']),
            'html_path': row['html_path'],
            'tables': row['tables'],
        }
        upsert_page(session, meta)
        count += 1
        if limit and count >= limit:
            break
    return count
