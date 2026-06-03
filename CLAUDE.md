# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (dev)
uvicorn backend.main:app --reload --port 8000

# Run via Docker
docker build -t muscu . && docker run -p 8000:8000 --env-file .env muscu
```

The app serves frontend static files AND the API from the same FastAPI process. FastAPI routes take priority; the static mount (`/`) is always last in `main.py`.

API docs available at `http://localhost:8000/docs` — use this to test endpoints before touching frontend.

## Environment

`.env` file required (never commit):
```
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...        # available for Whisper/voice features
```

Variables are read directly via `os.environ["ANTHROPIC_API_KEY"]` in `backend/ai.py` — no dotenv library, so the `.env` must be sourced or loaded by the process runner. Railway loads it from project settings.

## Architecture

**Single-process**: FastAPI (`backend/main.py`) serves both the REST API and all frontend HTML/JS files as static files. No build step — vanilla HTML + Tailwind CDN.

**Database**: SQLite at project root (`muscu.db`). Schema initialized on startup via `init_db()` in `database.py` using `CREATE TABLE IF NOT EXISTS`. No migration framework — add columns carefully or recreate.

**Frontend pages** (all standalone HTML, share `app.js`):
- `index.html` — session logging (main page)
- `exercises.html` — exercise library
- `history.html` — per-exercise history + Chart.js graphs
- `weekly.html` — weekly summary + Claude suggestions

**`frontend/app.js`** — shared API client (`api.*` methods) and utilities (`showToast`, `setLoading`, `todayISO`, `escapeHtml`). Loaded by all pages via `<script src="app.js">`.

## Database Schema (current)

```sql
exercises (id, name, description, muscles TEXT JSON, photo_path,
           last_session_date*, session_count*)   -- *computed in list_exercises()

sessions (id, date, exercise_id FK, sets, reps, weight_kg)  -- legacy global fields

session_sets (id, session_id FK CASCADE, set_number, reps, weight_kg)  -- per-set detail
```

`list_exercises()` does a LEFT JOIN to compute `last_session_date` and `session_count`. New sessions from the frontend send `sets_data: [{reps, weight_kg}]`; the backend derives legacy `sets/reps/weight_kg` fields automatically for backward compat.

## Claude AI Integration (`backend/ai.py`)

- **`detect_machine(image_base64)`** — vision call, returns `{name, muscles, tips}` or `None`
- **`weekly_suggestion(sessions)`** — text call, returns `{summary, suggestions[], next_week_focus}`
- Model: `claude-sonnet-4-6` for all calls
- Client is lazy-initialized (singleton `_client`)
- Both functions return parsed JSON dicts; strip markdown code fences if present

## UI/UX Rules

**Before any frontend component**, run the design system tool:
```bash
python3 .claude/skills/ui-ux-pro-max/scripts/search.py "fitness mobile dark" --design-system --stack html-tailwind
```

**Established design tokens** (do not deviate):
- Background: `#030712` (gray-950)
- Accent: `#F97316` (orange-500)
- Heading font: `Barlow Condensed` (class `heading`)
- Body font: `Barlow`
- Rounded cards: `rounded-xl`, inputs `min-h-[52px]`, action buttons `min-h-[64px]`
- Nav: `fixed bottom-0`, currently **3 tabs** (Séance / Historique / Semaine) — Exercices tab was removed

**No emojis as icons** — use Heroicons SVG inline. The SKILL.md pre-delivery checklist applies to all frontend work.

## Key Patterns

**Adding a new endpoint**: add Pydantic model → route in `main.py` → CRUD function in `database.py`. Import the DB function at the top of `main.py`.

**Exercise selection flow** (`index.html`): load all exercises with `GET /exercises` (includes `last_session_date`) → render recent (top 8 by date) + others grouped by first muscle → click selects → show 3 input-mode buttons (🎤 Dicter / 📷 Photo / ✏️ Manuel) → Manuel reveals the set-by-set form.

**Session save payload**: `{date, exercise_id, sets_data: [{reps, weight_kg}]}` — legacy `sets/reps/weight_kg` fields optional.

**Admin seed**: `POST /admin/seed` with header `X-Admin-Key: muscu-seed-2026` runs `seed_data.py` which generates ~9 months of synthetic workout history.
