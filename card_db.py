# card_db.py - simple SQLite card catalog helper

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel

from game_state import Rune, CardType

DB_PATH = Path("cards.db")


class CardRecord(BaseModel):
    card_id: str
    name: str
    card_type: CardType
    domain: Rune
    energy_cost: int = 0
    power_cost: int = 0
    might: Optional[int] = None
    tags: List[str] = []
    keywords: List[str] = []
    rules_text: Optional[str] = None
    set_name: Optional[str] = None


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the cards table if it doesn't exist."""
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cards (
                card_id    TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                card_type  TEXT NOT NULL,
                domain     TEXT NOT NULL,
                energy_cost INTEGER NOT NULL DEFAULT 0,
                power_cost  INTEGER NOT NULL DEFAULT 0,
                might       INTEGER,
                tags        TEXT,          -- JSON array
                keywords    TEXT,          -- JSON array
                rules_text  TEXT,
                set_name    TEXT
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_card(card: CardRecord) -> None:
    """Insert or update a card in the catalog."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO cards (
                card_id,
                name,
                card_type,
                domain,
                energy_cost,
                power_cost,
                might,
                tags,
                keywords,
                rules_text,
                set_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                name       = excluded.name,
                card_type  = excluded.card_type,
                domain     = excluded.domain,
                energy_cost= excluded.energy_cost,
                power_cost = excluded.power_cost,
                might      = excluded.might,
                tags       = excluded.tags,
                keywords   = excluded.keywords,
                rules_text = excluded.rules_text,
                set_name   = excluded.set_name;
            """,
            (
                card.card_id,
                card.name,
                card.card_type.value,
                card.domain.value,
                card.energy_cost,
                card.power_cost,
                card.might,
                json.dumps(card.tags),
                json.dumps(card.keywords),
                card.rules_text,
                card.set_name,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def row_to_card(row: sqlite3.Row) -> CardRecord:
    return CardRecord(
        card_id=row["card_id"],
        name=row["name"],
        card_type=CardType(row["card_type"]),
        domain=Rune(row["domain"]),
        energy_cost=row["energy_cost"],
        power_cost=row["power_cost"],
        might=row["might"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        keywords=json.loads(row["keywords"]) if row["keywords"] else [],
        rules_text=row["rules_text"],
        set_name=row["set_name"],
    )


def get_card(card_id: str) -> Optional[CardRecord]:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT * FROM cards WHERE card_id = ?;", (card_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return row_to_card(row)
    finally:
        conn.close()


def list_cards(
    card_type: Optional[CardType] = None,
    domain: Optional[Rune] = None,
    exclude_battlefields: bool = False,
) -> List[CardRecord]:
    conn = get_connection()
    try:
        query = "SELECT * FROM cards WHERE 1=1"
        params: list = []

        if card_type is not None:
            query += " AND card_type = ?"
            params.append(card_type.value)

        if domain is not None:
            query += " AND domain = ?"
            params.append(domain.value)

        if exclude_battlefields:
            query += " AND card_type != ?"
            params.append(CardType.BATTLEFIELD.value)

        cur = conn.execute(query + " ORDER BY energy_cost, name;", params)
        rows = cur.fetchall()
        return [row_to_card(r) for r in rows]
    finally:
        conn.close()


def count_cards() -> int:
    conn = get_connection()
    try:
        cur = conn.execute("SELECT COUNT(*) AS c FROM cards;")
        row = cur.fetchone()
        return row["c"]
    finally:
        conn.close()