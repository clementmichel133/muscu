import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "muscu.db"

# Default muscles per workout type (used when creating a new workout)
WORKOUT_TYPES = {
    "pecs_biceps":     ["pectoraux", "biceps"],
    "dos_triceps":     ["dos", "triceps"],
    "legs":            ["quadriceps", "ischio-jambiers", "fessiers"],
    "epaules_mollets": ["épaules", "mollets"],
    "custom":          [],
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Add a column to an existing table only if it is missing (idempotent migration)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_connection() as conn:

        # ── Legacy tables (unchanged schema, kept for backward compat) ──────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                id           INTEGER PRIMARY KEY,
                name         TEXT NOT NULL,
                description  TEXT,
                muscles      TEXT,
                photo_path   TEXT,
                instructions TEXT,
                image_url    TEXT,
                gif_url      TEXT,
                source       TEXT DEFAULT 'manual',
                equipment    TEXT
            )
        """)
        # Migrate existing DBs that have the old 5-column exercises schema
        for col, defn in [
            ("instructions", "TEXT"),
            ("image_url",    "TEXT"),
            ("gif_url",      "TEXT"),
            ("source",       "TEXT DEFAULT 'manual'"),
            ("equipment",    "TEXT"),
        ]:
            _ensure_column(conn, "exercises", col, defn)

        # Fix image_url records missing the GitHub raw prefix — log result at startup
        _IMAGE_PREFIX = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"
        _to_fix = conn.execute(
            "SELECT COUNT(*) FROM exercises WHERE image_url IS NOT NULL AND image_url != '' AND image_url NOT LIKE 'http%'"
        ).fetchone()[0]
        if _to_fix:
            conn.execute(
                f"""UPDATE exercises
                    SET image_url = '{_IMAGE_PREFIX}' || image_url,
                        gif_url   = '{_IMAGE_PREFIX}' || gif_url
                    WHERE image_url IS NOT NULL
                      AND image_url != ''
                      AND image_url NOT LIKE 'http%'"""
            )
            print(f"[init_db] {_to_fix} image URL(s) corrigée(s) avec le préfixe GitHub")
        else:
            print("[init_db] Images : toutes les URLs sont déjà correctes")
        # Nullify invalid image URLs (twitter/x.com/placeholder or non-github) from old exercisedb source
        _nulled = conn.execute(
            """SELECT COUNT(*) FROM exercises
               WHERE (image_url LIKE '%twitter%'
                   OR image_url LIKE '%x.com%'
                   OR image_url LIKE '%placeholder%'
                   OR image_url NOT LIKE '%github%')
                 AND image_url IS NOT NULL
                 AND image_url != ''
                 AND source = 'exercisedb'"""
        ).fetchone()[0]
        if _nulled:
            conn.execute(
                """UPDATE exercises
                   SET image_url = NULL, gif_url = NULL
                   WHERE (image_url LIKE '%twitter%'
                       OR image_url LIKE '%x.com%'
                       OR image_url LIKE '%placeholder%'
                       OR image_url NOT LIKE '%github%')
                     AND image_url IS NOT NULL
                     AND image_url != ''
                     AND source = 'exercisedb'"""
            )
            print(f"[init_db] {_nulled} URL(s) invalide(s) mises à NULL (source=exercisedb)")

        _samples = conn.execute(
            "SELECT id, name, image_url FROM exercises WHERE image_url IS NOT NULL LIMIT 5"
        ).fetchall()
        for _r in _samples:
            _url = _r[2] or ""
            print(f"[init_db] id={_r[0]} {_r[1]!r:40s} | http={_url.startswith('http')} | {_url[:70]}")

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
                id         INTEGER PRIMARY KEY,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                set_number INTEGER NOT NULL,
                reps       INTEGER NOT NULL,
                weight_kg  REAL NOT NULL
            )
        """)

        # ── New workout tables ───────────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id      INTEGER PRIMARY KEY,
                date    TEXT NOT NULL,
                type    TEXT NOT NULL,
                muscles TEXT,
                notes   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workout_exercises (
                id          INTEGER PRIMARY KEY,
                workout_id  INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
                exercise_id INTEGER NOT NULL REFERENCES exercises(id),
                order_num   INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sets (
                id                  INTEGER PRIMARY KEY,
                workout_exercise_id INTEGER NOT NULL
                                    REFERENCES workout_exercises(id) ON DELETE CASCADE,
                set_num             INTEGER NOT NULL,
                reps                INTEGER NOT NULL,
                weight_kg           REAL NOT NULL
            )
        """)

        # Indexes for the hot query paths
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workouts_date   ON workouts(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_we_workout      ON workout_exercises(workout_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_we_exercise     ON workout_exercises(exercise_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sets_we         ON sets(workout_exercise_id)")
        conn.commit()


# ── Exercises ───────────────────────────────────────────────────────────────

def create_exercise(
    name: str,
    description: str = None,
    muscles: list = None,
    photo_path: str = None,
    instructions: str = None,
    image_url: str = None,
    gif_url: str = None,
    source: str = "manual",
    equipment: str = None,
) -> dict:
    muscles_json = json.dumps(muscles, ensure_ascii=False) if muscles else None
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO exercises
               (name, description, muscles, photo_path, instructions, image_url, gif_url, source, equipment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, description, muscles_json, photo_path, instructions, image_url, gif_url, source, equipment),
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
    """Return all exercises with last_session_date and session_count from both
    the new workouts schema and the legacy sessions table."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT e.*,
                   COALESCE(
                       (SELECT MAX(w.date)
                        FROM workout_exercises we
                        JOIN workouts w ON w.id = we.workout_id
                        WHERE we.exercise_id = e.id),
                       (SELECT MAX(s.date) FROM sessions s WHERE s.exercise_id = e.id)
                   ) AS last_session_date,
                   (
                       SELECT COUNT(DISTINCT we.workout_id)
                       FROM workout_exercises we WHERE we.exercise_id = e.id
                   ) + (
                       SELECT COUNT(*) FROM sessions s WHERE s.exercise_id = e.id
                   ) AS session_count
            FROM exercises e
            ORDER BY e.name
        """).fetchall()
    return [_exercise_row(r) for r in rows]


def _exercise_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["muscles"] = json.loads(d["muscles"]) if d["muscles"] else []
    d.setdefault("last_session_date", None)
    d.setdefault("session_count", 0)
    d.setdefault("instructions", None)
    d.setdefault("image_url", None)
    d.setdefault("gif_url", None)
    d.setdefault("source", "manual")
    d.setdefault("equipment", None)
    return d


# ── Workouts ────────────────────────────────────────────────────────────────

def create_workout(date: str, type_: str, muscles: list = None, notes: str = None) -> dict:
    default_muscles = muscles if muscles is not None else WORKOUT_TYPES.get(type_, [])
    muscles_json = json.dumps(default_muscles, ensure_ascii=False)
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO workouts (date, type, muscles, notes) VALUES (?, ?, ?, ?)",
            (date, type_, muscles_json, notes),
        )
        conn.commit()
        return get_workout(cur.lastrowid)


def get_workout(workout_id: int) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM workouts WHERE id = ?", (workout_id,)).fetchone()
        if row is None:
            return None
        workout = _workout_row(row)
        workout["exercises"] = _load_workout_exercises(conn, workout_id)
    return workout


def get_or_create_workout(date: str, type_: str, muscles: list = None) -> dict:
    """Return today's workout of this type if it exists, otherwise create one."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM workouts WHERE date = ? AND type = ? ORDER BY id DESC LIMIT 1",
            (date, type_),
        ).fetchone()
        if row is not None:
            workout = _workout_row(row)
            workout["exercises"] = _load_workout_exercises(conn, row["id"])
            return workout
    return create_workout(date, type_, muscles)


def list_workouts(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM workouts ORDER BY date DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            w = _workout_row(row)
            w["exercises"] = _load_workout_exercises(conn, row["id"])
            result.append(w)
    return result


def list_workouts_for_week(week_start: str, week_end: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM workouts WHERE date BETWEEN ? AND ? ORDER BY date, id",
            (week_start, week_end),
        ).fetchall()
        result = []
        for row in rows:
            w = _workout_row(row)
            w["exercises"] = _load_workout_exercises(conn, row["id"])
            result.append(w)
    return result


def _workout_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["muscles"] = json.loads(d["muscles"]) if d["muscles"] else []
    return d


def _load_workout_exercises(conn: sqlite3.Connection, workout_id: int) -> list[dict]:
    we_rows = conn.execute(
        """SELECT we.id, we.workout_id, we.exercise_id, we.order_num,
                  e.name, e.muscles, e.description, e.gif_url, e.instructions, e.equipment
           FROM workout_exercises we
           JOIN exercises e ON e.id = we.exercise_id
           WHERE we.workout_id = ?
           ORDER BY we.order_num, we.id""",
        (workout_id,),
    ).fetchall()
    result = []
    for we in we_rows:
        item = dict(we)
        item["muscles"] = json.loads(item["muscles"]) if item["muscles"] else []
        item["sets"] = _load_sets(conn, we["id"])
        result.append(item)
    return result


def _load_sets(conn: sqlite3.Connection, workout_exercise_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM sets WHERE workout_exercise_id = ? ORDER BY set_num",
        (workout_exercise_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Workout exercises ────────────────────────────────────────────────────────

def add_exercise_to_workout(workout_id: int, exercise_id: int) -> dict:
    """Append an exercise to a workout and return the workout_exercise row with sets=[]."""
    with get_connection() as conn:
        max_order = conn.execute(
            "SELECT COALESCE(MAX(order_num), 0) FROM workout_exercises WHERE workout_id = ?",
            (workout_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO workout_exercises (workout_id, exercise_id, order_num) VALUES (?, ?, ?)",
            (workout_id, exercise_id, max_order + 1),
        )
        conn.commit()
        we_id = cur.lastrowid
        row = conn.execute(
            """SELECT we.id, we.workout_id, we.exercise_id, we.order_num,
                      e.name, e.muscles, e.description, e.gif_url, e.instructions, e.equipment
               FROM workout_exercises we
               JOIN exercises e ON e.id = we.exercise_id
               WHERE we.id = ?""",
            (we_id,),
        ).fetchone()
        item = dict(row)
        item["muscles"] = json.loads(item["muscles"]) if item["muscles"] else []
        item["sets"] = []
    return item


def remove_exercise_from_workout(workout_exercise_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM workout_exercises WHERE id = ?", (workout_exercise_id,))
        conn.commit()


# ── Sets ─────────────────────────────────────────────────────────────────────

def add_set(workout_exercise_id: int, reps: int, weight_kg: float) -> dict:
    with get_connection() as conn:
        next_num = conn.execute(
            "SELECT COALESCE(MAX(set_num), 0) + 1 FROM sets WHERE workout_exercise_id = ?",
            (workout_exercise_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO sets (workout_exercise_id, set_num, reps, weight_kg) VALUES (?, ?, ?, ?)",
            (workout_exercise_id, next_num, reps, weight_kg),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sets WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def update_set(set_id: int, reps: int, weight_kg: float) -> dict | None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE sets SET reps = ?, weight_kg = ? WHERE id = ?",
            (reps, weight_kg, set_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sets WHERE id = ?", (set_id,)).fetchone()
    return dict(row) if row else None


def delete_set(set_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM sets WHERE id = ?", (set_id,))
        conn.commit()


# ── Exercise history ─────────────────────────────────────────────────────────

def get_last_workout_for_exercise(exercise_id: int) -> dict | None:
    """Most recent session for this exercise (from new workouts schema).
    Returns {date, workout_id, sets} or None."""
    with get_connection() as conn:
        row = conn.execute(
            """SELECT we.id AS we_id, w.date, w.id AS workout_id
               FROM workout_exercises we
               JOIN workouts w ON w.id = we.workout_id
               WHERE we.exercise_id = ?
               ORDER BY w.date DESC, we.id DESC
               LIMIT 1""",
            (exercise_id,),
        ).fetchone()
        if row is None:
            return None
        result = {"date": row["date"], "workout_id": row["workout_id"]}
        result["sets"] = _load_sets(conn, row["we_id"])
    return result


def get_exercise_history(exercise_id: int, limit: int = 10) -> list[dict]:
    """Last N appearances of this exercise across workouts, newest first.
    Each entry has {date, workout_id, type, sets}."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT we.id AS we_id, w.date, w.id AS workout_id, w.type
               FROM workout_exercises we
               JOIN workouts w ON w.id = we.workout_id
               WHERE we.exercise_id = ?
               ORDER BY w.date DESC, we.id DESC
               LIMIT ?""",
            (exercise_id, limit),
        ).fetchall()
        result = []
        for row in rows:
            entry = {
                "date":       row["date"],
                "workout_id": row["workout_id"],
                "type":       row["type"],
                "sets":       _load_sets(conn, row["we_id"]),
            }
            result.append(entry)
    return result


def delete_workout(workout_id: int) -> None:
    """Delete a workout and cascade to workout_exercises + sets."""
    with get_connection() as conn:
        conn.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))
        conn.commit()


def search_exercises(muscle: str = None, search: str = None) -> list[dict]:
    """Filter exercises by muscle substring and/or name substring.
    Falls back to list_exercises() when both args are None."""
    conditions: list[str] = []
    params: list = []
    if muscle:
        conditions.append("LOWER(COALESCE(e.muscles, '')) LIKE LOWER(?)")
        params.append(f"%{muscle}%")
    if search:
        conditions.append("LOWER(e.name) LIKE LOWER(?)")
        params.append(f"%{search}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_connection() as conn:
        rows = conn.execute(f"""
            SELECT e.*,
                   COALESCE(
                       (SELECT MAX(w.date)
                        FROM workout_exercises we
                        JOIN workouts w ON w.id = we.workout_id
                        WHERE we.exercise_id = e.id),
                       (SELECT MAX(s.date) FROM sessions s WHERE s.exercise_id = e.id)
                   ) AS last_session_date,
                   (
                       SELECT COUNT(DISTINCT we.workout_id)
                       FROM workout_exercises we WHERE we.exercise_id = e.id
                   ) + (
                       SELECT COUNT(*) FROM sessions s WHERE s.exercise_id = e.id
                   ) AS session_count
            FROM exercises e
            {where}
            ORDER BY e.name
        """, params).fetchall()
    return [_exercise_row(r) for r in rows]


# ── Legacy sessions (backward compat — existing endpoints unchanged) ─────────

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
            """SELECT s.* FROM sessions s
               JOIN exercises e ON e.id = s.exercise_id
               WHERE LOWER(e.name) = LOWER(?)
               ORDER BY s.date DESC""",
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
            """SELECT s.*, e.name AS exercise_name, e.muscles
               FROM sessions s
               JOIN exercises e ON e.id = s.exercise_id
               WHERE s.date BETWEEN ? AND ?
               ORDER BY s.date, e.name""",
            (week_start, week_end),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["muscles"] = json.loads(d["muscles"]) if d["muscles"] else []
        result.append(d)
    return result
