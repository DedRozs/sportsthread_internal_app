# DBFunctions.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import pymysql
from pymysql.cursors import DictCursor

# Single source of truth for the SQL text (keeps column order/names + ORDER BY)
from app.roster.sql_text import base_select, partner_logo_select

# Timeouts & retries per spec §10
CONNECT_TIMEOUT_S = 30
READ_TIMEOUT_S = 60
WRITE_TIMEOUT_S = 60
RETRIES = 3
BACKOFF_BASE_S = 0.75  # 0.75s, 1.5s, 3.0s


class DBError(RuntimeError):
    """Raised for configuration or query failures."""


def _conn_params() -> Dict[str, Any]:
    """
    Build connection parameters from environment variables. No secrets are hard-coded.
    Expected (loaded via app.main -> load_dotenv in dev):
      DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
    """
    try:
        return {
            "host": os.environ["DB_HOST"],
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.environ["DB_USER"],
            "password": os.environ["DB_PASSWORD"],
            "database": os.environ.get("DB_NAME", "sportsthreadprod"),
            "cursorclass": DictCursor,
            "connect_timeout": CONNECT_TIMEOUT_S,
            "read_timeout": READ_TIMEOUT_S,
            "write_timeout": WRITE_TIMEOUT_S,
            "charset": "utf8mb4",
            "autocommit": True,
        }
    except KeyError as ke:
        missing = str(ke).strip("'")
        raise DBError(f"Missing required environment variable: {missing}") from None


def _connect() -> pymysql.connections.Connection:
    return pymysql.connect(**_conn_params())


def health_check() -> bool:
    """
    Lightweight connectivity probe. Returns True when a simple round-trip succeeds.
    Retries with exponential backoff per spec.
    """
    for attempt in range(1, RETRIES + 1):
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return True
        except Exception:
            if attempt >= RETRIES:
                return False
            time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
    return False  # pragma: no cover


def _run_query(sql: str) -> List[Dict[str, Any]]:
    last_err: Optional[BaseException] = None
    for attempt in range(1, RETRIES + 1):
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
                    return list(rows)
        except Exception as exc:
            last_err = exc
            if attempt >= RETRIES:
                break
            time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))
    raise DBError(f"Query failed after {RETRIES} attempts: {last_err}")


def fetch_roster(event_id: int, team_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Run the canonical roster query and return rows as dicts keyed EXACTLY like the spec:

      Event_ID, Event_Name, Team_Name, Team_ID, Division, User_ID, Name,
      Usertype_ID, Phone, Email, Profile_Pic, Jersey_Num, Birthday

    The SQL string (including ORDER BY etr.teamId, u.id) comes from app.roster.sql_text.base_select.
    """
    sql = base_select(event_id=event_id, team_id=team_id)
    return _run_query(sql)


def _normalize_partner_logo_url(raw: str) -> str:
    """
    Apply Sports Thread file CDN rules:
      - '/path'           -> 'https://files.sportsthread.com/path'
      - 'http(s)://...'   -> unchanged
      - 'foo/bar.png'     -> 'https://files.sportsthread.com/foo/bar.png'
    """
    s = raw.strip()
    if s.startswith("/"):
        return f"https://files.sportsthread.com{s}"
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return f"https://files.sportsthread.com/{s}"


def fetch_partner_logo(event_id: int) -> Optional[str]:
    """
    Return the normalized partner logo URL for a given event, or None if not configured.
    Uses the canonical SQL in app.roster.sql_text.partner_logo_select.
    """
    sql = partner_logo_select(event_id=event_id)
    rows = _run_query(sql)
    if not rows:
        return None
    url = rows[0].get("Partner_Logo_URL")
    if not url or not str(url).strip():
        return None
    return _normalize_partner_logo_url(str(url).strip())


__all__ = ["DBError", "health_check", "fetch_roster", "fetch_partner_logo"]
