# DBFunctions.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple



import pymysql
from pymysql.cursors import DictCursor

# Use the single source-of-truth SQL text

# ---- Env / config (no secrets hard-coded) ----
# Expected env vars (dev via .env which app.main already loads): :contentReference[oaicite:8]{index=8}
#   DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
# Timeouts & retries per spec §10. :contentReference[oaicite:9]{index=9}
CONNECT_TIMEOUT_S = 30
READ_TIMEOUT_S = 60
WRITE_TIMEOUT_S = 60
RETRIES = 3
BACKOFF_BASE_S = 0.75

class DBError(RuntimeError):
    pass

def _conn_params() -> Dict[str, Any]:
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
    return False  # unreachable

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
    Returns rows with the exact columns required by the PDF pipeline:
      Event_ID, Event_Name, Team_Name, Team_ID, Division, User_ID, Name,
      Usertype_ID, Phone, Email, Profile_Pic, Jersey_Num, Birthday
    The SQL string is sourced from app.roster.sql_text.base_select().  :contentReference[oaicite:10]{index=10}
    """
    sql = base_select(event_id=event_id, team_id=team_id)
    return _run_query(sql)

def base_select(event_id: int, team_id: int | None) -> str:
    base = """
    SELECT
        e.ID as Event_ID,
        e.name as Event_Name,
        t.name as Team_Name,
        t.id as "Team_ID",
        ld.name as Division,
        u.id as User_ID,
        CONCAT(u.firstName, " ", u.lastName) as Name,
        u.userTypeID as Usertype_ID,
        u.phone as Phone,
        u.email as Email,
        u.avatarURL as Profile_Pic,
        etr.jerseyNumber as Jersey_Num,
        u.birthday as Birthday
    FROM
        sportsthreadprod.Events e
    INNER JOIN sportsthreadprod.EventTeamRoster etr ON etr.eventId = e.ID
    INNER JOIN sportsthreadprod.Teams t ON etr.teamId = t.id
    INNER JOIN sportsthreadprod.`User` u ON etr.userId = u.id
    INNER JOIN sportsthreadprod.LookupDivisions ld ON t.divisionID = ld.id
    """
    if team_id is not None:
        return base + f" WHERE e.id={event_id} AND etr.teamId={team_id} ORDER BY etr.teamId, u.id;"
    return base + f" WHERE e.id={event_id} ORDER BY etr.teamId, u.id;"

def partner_logo_select(event_id: int) -> str:
    """
    Return SQL to fetch the partner name and logo URL for a specific event.
    Columns (and order) are intentional for determinism.
    """
    return f"""
    SELECT
        e.ID       AS Event_ID,
        p.name     AS Partner_Name,
        p.logo     AS Partner_Logo_URL
    FROM sportsthreadprod.Events e
    INNER JOIN sportsthreadprod.Partners p
        ON e.partnerID = p.ID
    WHERE e.ID = {int(event_id)}
    LIMIT 1;
    """.strip()