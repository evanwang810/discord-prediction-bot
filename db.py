import sqlite3
import aiosqlite
from contextlib import asynccontextmanager
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS servers (
    guild_id INTEGER PRIMARY KEY,
    currency_name TEXT NOT NULL DEFAULT 'credits',
    starting_balance INTEGER NOT NULL DEFAULT 1000,
    inflation_amount INTEGER NOT NULL DEFAULT 0,
    inflation_days INTEGER NOT NULL DEFAULT 7,
    initial_subsidy INTEGER NOT NULL DEFAULT 5000,
    tax_percent REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    balance INTEGER NOT NULL,
    last_inflation TEXT NOT NULL,
    last_trade_at TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_username ON accounts (guild_id, username);

CREATE TABLE IF NOT EXISTS markets (
    market_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    outcome TEXT,
    liquidity REAL NOT NULL,
    subsidy INTEGER NOT NULL DEFAULT 0,
    yes_shares REAL NOT NULL DEFAULT 0,
    no_shares REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_markets_guild_status ON markets (guild_id, status);

CREATE TABLE IF NOT EXISTS positions (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    market_id INTEGER NOT NULL,
    yes_shares REAL NOT NULL DEFAULT 0,
    no_shares REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, market_id)
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    market_id INTEGER NOT NULL,
    outcome TEXT NOT NULL,
    shares REAL NOT NULL,
    cost INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'buy',
    price_at_trade REAL,
    price_after REAL,
    tax_paid INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transfers (
    transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    from_user INTEGER NOT NULL,
    to_user INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    snap_date TEXT NOT NULL,
    net_worth REAL NOT NULL,
    PRIMARY KEY (guild_id, user_id, snap_date)
);
"""

# ALTER TABLE migrations for users who had an earlier version of the schema.
_ADDS = [
    ("servers", "initial_subsidy", "INTEGER NOT NULL DEFAULT 5000"),
    ("servers", "tax_percent", "REAL NOT NULL DEFAULT 0"),
    ("accounts", "last_trade_at", "TEXT"),
    ("trades", "price_at_trade", "REAL"),
    ("trades", "price_after", "REAL"),
    ("trades", "tax_paid", "INTEGER NOT NULL DEFAULT 0"),
    ("trades", "kind", "TEXT NOT NULL DEFAULT 'buy'"),
    ("markets", "subsidy", "INTEGER NOT NULL DEFAULT 0"),
]

_DROPS = [
    ("accounts", "password_hash"),
]


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.executescript(SCHEMA)
        for table, col, decl in _ADDS:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass
        for table, col in _DROPS:
            try:
                await db.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        await db.commit()


@asynccontextmanager
async def connect():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
