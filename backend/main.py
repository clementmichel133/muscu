from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

from backend.database import (
    init_db,
    create_exercise,
    list_exercises,
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


# --- Pydantic models ---

class ExerciseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    muscles: Optional[list[str]] = None


class ExerciseDetectRequest(BaseModel):
    image_base64: str


class SetItem(BaseModel):
    reps: int
    weight_kg: float


class SessionCreate(BaseModel):
    date: str  # YYYY-MM-DD
    exercise_id: int
    sets_data: Optional[list[SetItem]] = None
    # Legacy fields kept for backward compatibility
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight_kg: Optional[float] = None


# --- Endpoints ---

@app.get("/exercises")
def get_exercises():
    return list_exercises()


@app.post("/exercises", status_code=201)
def post_exercise(body: ExerciseCreate):
    return create_exercise(body.name, body.description, body.muscles)


@app.post("/exercises/detect")
def post_exercise_detect(body: ExerciseDetectRequest):
    from backend.ai import detect_machine
    result = detect_machine(body.image_base64)
    if result is None:
        raise HTTPException(status_code=422, detail="Image non reconnue comme machine de musculation")
    return result


@app.post("/sessions", status_code=201)
def post_session(body: SessionCreate):
    sets_data = [s.model_dump() for s in body.sets_data] if body.sets_data else None
    sets = body.sets
    reps = body.reps
    weight_kg = body.weight_kg
    # Derive legacy fields from sets_data when not provided
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
    from backend.ai import weekly_suggestion

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


_ADMIN_KEY = "muscu-seed-2026"


@app.post("/admin/seed")
def post_admin_seed(x_admin_key: str = Header(...)):
    if x_admin_key != _ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Clé admin invalide")
    try:
        from backend.seed_data import main as run_seed
        run_seed()
        return {"status": "ok", "detail": "Seed exécuté avec succès"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Doit être monté en dernier — les routes API ont la priorité
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
