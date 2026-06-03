import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "muscu.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT,
                muscles     TEXT,
                photo_path  TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY,
                date        TEXT NOT NULL,
                exercise_id INTEGER REFERENCES exercises(id),
                sets        INTEGER,
                reps        INTEGER,
                weight_kg   REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS session_sets (
                id          INTEGER PRIMARY KEY,
                session_id  INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                set_number  INTEGER NOT NULL,
                reps        INTEGER NOT NULL,
                weight_kg   REAL NOT NULL
            )
        """)
        conn.commit()


# --- Exercises ---

def create_exercise(name: str, description: str = None, muscles: list = None, photo_path: str = None) -> dict:
    muscles_json = json.dumps(muscles) if muscles else None
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO exercises (name, description, muscles, photo_path) VALUES (?, ?, ?, ?)",
            (name, description, muscles_json, photo_path),
        )
        conn.commit()
        return get_exercise(cur.lastrowid)


def get_exercise(exercise_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM exercises WHERE id = ?", (exercise_id,)).fetchone()
    if row is None:
        return None
    return _exercise_row(row)


def list_exercises() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.*,
                   MAX(s.date) AS last_session_date,
                   COUNT(s.id) AS session_count
            FROM exercises e
            LEFT JOIN sessions s ON s.exercise_id = e.id
            GROUP BY e.id
            ORDER BY e.name
        """).fetchall()
    return [_exercise_row(r) for r in rows]


def _exercise_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["muscles"] = json.loads(d["muscles"]) if d["muscles"] else []
    if "last_session_date" not in d:
        d["last_session_date"] = None
    if "session_count" not in d:
        d["session_count"] = 0
    return d


# --- Sessions ---

def create_session(
    date: str,
    exercise_id: int,
    sets: int = None,
    reps: int = None,
    weight_kg: float = None,
    sets_data: list = None,
) -> dict:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (date, exercise_id, sets, reps, weight_kg) VALUES (?, ?, ?, ?, ?)",
            (date, exercise_id, sets, reps, weight_kg),
        )
        session_id = cur.lastrowid
        if sets_data:
            for i, s in enumerate(sets_data, start=1):
                conn.execute(
                    "INSERT INTO session_sets (session_id, set_number, reps, weight_kg) VALUES (?, ?, ?, ?)",
                    (session_id, i, s["reps"], s["weight_kg"]),
                )
        conn.commit()
        return get_session(session_id)


def get_session(session_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        sets_rows = conn.execute(
            "SELECT set_number, reps, weight_kg FROM session_sets WHERE session_id = ? ORDER BY set_number",
            (session_id,),
        ).fetchall()
        result["sets_data"] = [dict(r) for r in sets_rows]
    return result


def list_sessions_by_exercise(exercise_name: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.* FROM sessions s
            JOIN exercises e ON e.id = s.exercise_id
            WHERE LOWER(e.name) = LOWER(?)
            ORDER BY s.date DESC
            """,
            (exercise_name,),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            sets_rows = conn.execute(
                "SELECT set_number, reps, weight_kg FROM session_sets WHERE session_id = ? ORDER BY set_number",
                (d["id"],),
            ).fetchall()
            d["sets_data"] = [dict(r) for r in sets_rows]
            result.append(d)
    return result


def list_sessions_for_week(week_start: str, week_end: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.*, e.name AS exercise_name, e.muscles
            FROM sessions s
            JOIN exercises e ON e.id = s.exercise_id
            WHERE s.date BETWEEN ? AND ?
            ORDER BY s.date, e.name
            """,
            (week_start, week_end),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["muscles"] = json.loads(d["muscles"]) if d["muscles"] else []
        result.append(d)
    return result
