import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

from database import (
    # init
    init_db,
    WORKOUT_TYPES,
    # exercises
    create_exercise,
    get_exercise,
    list_exercises,
    search_exercises,
    # workouts
    create_workout,
    get_workout,
    get_or_create_workout,
    list_workouts,
    list_workouts_for_week,
    delete_workout,
    # workout exercises
    add_exercise_to_workout,
    remove_exercise_from_workout,
    # sets
    add_set,
    update_set,
    delete_set,
    # exercise history
    get_last_workout_for_exercise,
    get_exercise_history,
    # legacy sessions
    create_session,
    list_sessions_by_exercise,
    list_sessions_for_week,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Muscu API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──────────────────────────────────────────────────────────

class ExerciseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    muscles: Optional[list[str]] = None
    instructions: Optional[str] = None
    image_url: Optional[str] = None
    gif_url: Optional[str] = None
    source: str = "manual"
    equipment: Optional[str] = None


class ExerciseDetectRequest(BaseModel):
    image_base64: str


class ExerciseIdentifyRequest(BaseModel):
    text: Optional[str] = None
    image_base64: Optional[str] = None


class WorkoutCreate(BaseModel):
    date: str                              # YYYY-MM-DD
    type: str                              # pecs_biceps | dos_triceps | legs | epaules_mollets | custom
    muscles: Optional[list[str]] = None   # required when type == "custom"
    notes: Optional[str] = None


class WorkoutExerciseAdd(BaseModel):
    exercise_id: int


class SetCreate(BaseModel):
    reps: int
    weight_kg: float


class SetUpdate(BaseModel):
    reps: int
    weight_kg: float


# Legacy models kept unchanged
class SetItem(BaseModel):
    reps: int
    weight_kg: float


class SessionCreate(BaseModel):
    date: str
    exercise_id: int
    sets_data: Optional[list[SetItem]] = None
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight_kg: Optional[float] = None


# ── Helper ───────────────────────────────────────────────────────────────────

def _exercisedb_to_local(ex: dict) -> dict:
    """Convert an ExerciseDB API object to the local exercise dict shape."""
    muscles = list({ex.get("target", "")} | set(ex.get("secondaryMuscles", [])))
    muscles = [m for m in muscles if m]
    instructions_raw = ex.get("instructions", [])
    instructions = (
        "\n".join(f"{i+1}. {s}" for i, s in enumerate(instructions_raw))
        if instructions_raw else None
    )
    return {
        "id": None,                          # not yet saved in local DB
        "name": ex.get("name", ""),
        "description": None,
        "muscles": muscles,
        "photo_path": None,
        "instructions": instructions,
        "image_url": ex.get("gifUrl"),
        "gif_url": ex.get("gifUrl"),
        "source": "exercisedb",
        "equipment": ex.get("equipment"),
        "last_session_date": None,
        "session_count": 0,
        # Extra fields from ExerciseDB kept for frontend use
        "exercisedb_id": ex.get("id"),
        "body_part": ex.get("bodyPart"),
    }


# ── Exercises ────────────────────────────────────────────────────────────────

@app.get("/exercises")
def get_exercises_list():
    return list_exercises()


@app.get("/exercises/{exercise_id}")
def get_exercise_by_id(exercise_id: int):
    ex = get_exercise(exercise_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    return ex


@app.get("/exercises/{exercise_id}/history")
def get_exercise_history_route(exercise_id: int, limit: int = 10):
    ex = get_exercise(exercise_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    return get_exercise_history(exercise_id, limit=limit)


@app.post("/exercises/{exercise_id}/tip")
def post_exercise_tip(exercise_id: int):
    """Generate a personalised coaching tip via Claude based on the user's history."""
    from ai import generate_exercise_tip
    ex = get_exercise(exercise_id)
    if ex is None:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    history = get_exercise_history(exercise_id, limit=5)
    tip = generate_exercise_tip(ex, history)
    return {"tip": tip}


@app.get("/exercises/{exercise_id}/last-workout")
def get_exercise_last_workout(exercise_id: int):
    result = get_last_workout_for_exercise(exercise_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Aucune séance trouvée pour cet exercice")
    return result


@app.post("/exercises", status_code=201)
def post_exercise(body: ExerciseCreate):
    return create_exercise(
        body.name, body.description, body.muscles,
        instructions=body.instructions, image_url=body.image_url,
        gif_url=body.gif_url, source=body.source, equipment=body.equipment,
    )


@app.post("/exercises/detect")
def post_exercise_detect(body: ExerciseDetectRequest):
    from ai import detect_machine
    result = detect_machine(body.image_base64)
    if result is None:
        raise HTTPException(status_code=422, detail="Image non reconnue comme machine de musculation")
    return result


@app.post("/exercises/identify")
def post_exercise_identify(body: ExerciseIdentifyRequest):
    """Identify an exercise from text or photo, then search ExerciseDB for enriched data.

    Returns:
        identified_name, confidence, muscles, gif_url, description,
        exercise_db_match (raw ExerciseDB object or null)
    """
    if not body.text and not body.image_base64:
        raise HTTPException(status_code=422, detail="Fournir 'text' ou 'image_base64'")

    from ai import (
        identify_exercise_from_text,
        identify_exercise_from_photo,
        search_exercisedb,
    )

    # Step 1 — Claude identifies the canonical exercise name
    try:
        if body.image_base64:
            identification = identify_exercise_from_photo(body.image_base64)
        else:
            identification = identify_exercise_from_text(body.text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Erreur Claude : {exc}")

    identified_name = identification.get("name", "")
    confidence = identification.get("confidence", "medium")

    # Step 2 — ExerciseDB lookup (optional, requires RAPIDAPI_KEY)
    api_key = os.getenv("RAPIDAPI_KEY")
    exercise_db_match = None
    muscles: list[str] = []
    gif_url: str | None = None
    description: str | None = None

    if api_key and identified_name:
        results = search_exercisedb(identified_name, api_key, limit=3)
        if results:
            best = results[0]
            exercise_db_match = best
            muscles = list({best.get("target", "")} | set(best.get("secondaryMuscles", [])))
            muscles = [m for m in muscles if m]
            gif_url = best.get("gifUrl")
            instructions_raw = best.get("instructions", [])
            description = (
                "\n".join(f"{i+1}. {s}" for i, s in enumerate(instructions_raw))
                if instructions_raw else None
            )

    return {
        "identified_name": identified_name,
        "confidence": confidence,
        "exercise_db_match": exercise_db_match,
        "muscles": muscles,
        "gif_url": gif_url,
        "description": description,
    }


@app.get("/exercise-library")
def get_exercise_library(muscle: Optional[str] = None, search: Optional[str] = None):
    """Search exercise library. Returns local DB results first; if fewer than 3
    local hits and RAPIDAPI_KEY is set, also returns remote ExerciseDB results.

    Response: {"local": [...], "remote": [...]}
    """
    local = search_exercises(muscle=muscle, search=search)

    remote: list[dict] = []
    api_key = os.getenv("RAPIDAPI_KEY")
    if api_key and search and len(local) < 3:
        from ai import search_exercisedb
        raw_results = search_exercisedb(search, api_key, limit=8)
        # Exclude any exercise already present locally (by name, case-insensitive)
        local_names = {ex["name"].lower() for ex in local}
        remote = [
            _exercisedb_to_local(r)
            for r in raw_results
            if r.get("name", "").lower() not in local_names
        ]

    return {"local": local, "remote": remote}


# ── Workouts ─────────────────────────────────────────────────────────────────

@app.get("/workouts")
def get_workouts(limit: int = 20, date: Optional[str] = None):
    """List recent workouts. Optionally filter by exact date."""
    if date:
        week = list_workouts_for_week(date, date)
        return week
    return list_workouts(limit=limit)


@app.post("/workouts", status_code=201)
def post_workout(body: WorkoutCreate):
    """Get today's workout of this type (if it exists) or create a new one.
    This is the main entry point: tap a workout type → open/create session."""
    known_types = set(WORKOUT_TYPES.keys())
    if body.type not in known_types:
        raise HTTPException(
            status_code=422,
            detail=f"Type inconnu. Valeurs acceptées : {sorted(known_types)}",
        )
    if body.type == "custom" and not body.muscles:
        raise HTTPException(status_code=422, detail="muscles requis pour le type 'custom'")

    return get_or_create_workout(body.date, body.type, muscles=body.muscles)


@app.get("/workouts/{workout_id}")
def get_workout_by_id(workout_id: int):
    workout = get_workout(workout_id)
    if workout is None:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    return workout


@app.delete("/workouts/{workout_id}", status_code=204)
def delete_workout_by_id(workout_id: int):
    if get_workout(workout_id) is None:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    delete_workout(workout_id)


@app.post("/workouts/{workout_id}/exercises", status_code=201)
def post_workout_exercise(workout_id: int, body: WorkoutExerciseAdd):
    if get_workout(workout_id) is None:
        raise HTTPException(status_code=404, detail="Séance introuvable")
    if get_exercise(body.exercise_id) is None:
        raise HTTPException(status_code=404, detail="Exercice introuvable")
    return add_exercise_to_workout(workout_id, body.exercise_id)


# ── Workout exercises ────────────────────────────────────────────────────────

@app.delete("/workout-exercises/{workout_exercise_id}", status_code=204)
def delete_workout_exercise(workout_exercise_id: int):
    remove_exercise_from_workout(workout_exercise_id)


# ── Sets ─────────────────────────────────────────────────────────────────────

@app.post("/workout-exercises/{workout_exercise_id}/sets", status_code=201)
def post_set(workout_exercise_id: int, body: SetCreate):
    return add_set(workout_exercise_id, body.reps, body.weight_kg)


@app.put("/sets/{set_id}")
def put_set(set_id: int, body: SetUpdate):
    result = update_set(set_id, body.reps, body.weight_kg)
    if result is None:
        raise HTTPException(status_code=404, detail="Série introuvable")
    return result


@app.delete("/sets/{set_id}", status_code=204)
def delete_set_by_id(set_id: int):
    delete_set(set_id)


# ── Legacy sessions (backward compat — all existing callers unchanged) ────────

@app.post("/sessions", status_code=201)
def post_session(body: SessionCreate):
    sets_data = [s.model_dump() for s in body.sets_data] if body.sets_data else None
    sets = body.sets
    reps = body.reps
    weight_kg = body.weight_kg
    if sets_data:
        if sets is None:
            sets = len(sets_data)
        if reps is None:
            reps = sets_data[0]["reps"]
        if weight_kg is None:
            weight_kg = sets_data[0]["weight_kg"]
    return create_session(body.date, body.exercise_id, sets, reps, weight_kg, sets_data)


@app.get("/sessions/{exercise_name}")
def get_sessions(exercise_name: str):
    sessions = list_sessions_by_exercise(exercise_name)
    if not sessions:
        raise HTTPException(status_code=404, detail=f"Aucune séance trouvée pour '{exercise_name}'")
    return sessions


@app.get("/weekly-summary")
def get_weekly_summary(week_start: Optional[str] = None, week_end: Optional[str] = None):
    from ai import weekly_suggestion

    if week_start is None or week_end is None:
        today = date.today()
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        week_end = (today + timedelta(days=6 - today.weekday())).isoformat()

    sessions = list_sessions_for_week(week_start, week_end)
    try:
        suggestions = weekly_suggestion(sessions)
    except NotImplementedError:
        suggestions = None
    return {
        "week_start": week_start,
        "week_end": week_end,
        "sessions": sessions,
        "suggestions": suggestions,
    }


# ── Admin ─────────────────────────────────────────────────────────────────────

_ADMIN_KEY = "muscu-seed-2026"


@app.get("/debug/images")
def debug_images():
    """Diagnostic: return the first 5 exercises that have an image_url, with validation."""
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(str(Path(__file__).parent.parent / "muscu.db"))
    conn.row_factory = _sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, image_url FROM exercises WHERE image_url IS NOT NULL LIMIT 5"
    ).fetchall()
    total_with_img = conn.execute(
        "SELECT COUNT(*) FROM exercises WHERE image_url IS NOT NULL AND image_url != ''"
    ).fetchone()[0]
    http_ok = conn.execute(
        "SELECT COUNT(*) FROM exercises WHERE image_url LIKE 'http%'"
    ).fetchone()[0]
    conn.close()
    return {
        "total_with_image_url": total_with_img,
        "starts_with_http": http_ok,
        "samples": [
            {
                "id":              r["id"],
                "name":            r["name"],
                "image_url":       r["image_url"],
                "starts_with_http": (r["image_url"] or "").startswith("http"),
            }
            for r in rows
        ],
    }


@app.post("/admin/seed")
def post_admin_seed(x_admin_key: str = Header(...)):
    if x_admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Clé admin invalide")
    try:
        from seed_data import main as run_seed
        run_seed()
        return {"status": "ok", "detail": "Seed exécuté avec succès"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Doit être monté en dernier — les routes API ont la priorité
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
