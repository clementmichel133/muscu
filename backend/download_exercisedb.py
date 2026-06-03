#!/usr/bin/env python3
"""
Télécharge le dataset free-exercise-db (GitHub) et l'importe dans la BDD locale.
Aucune clé API requise.

Usage (depuis la racine du projet) :
    python backend/download_exercisedb.py

Options :
    --from-cache   Saute le téléchargement, relit backend/exercisedb_cache.json
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from database import get_connection, init_db

CACHE_PATH   = Path(__file__).parent / "exercisedb_cache.json"
DATASET_URL  = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
IMAGE_PREFIX = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/exercises/"


# ── Téléchargement ────────────────────────────────────────────────────────────

def fetch_dataset() -> list[dict]:
    print("Téléchargement depuis GitHub (free-exercise-db)…")
    with urllib.request.urlopen(DATASET_URL, timeout=30) as resp:
        data = json.loads(resp.read())
    print(f"  → {len(data)} exercices reçus")
    return data


def save_cache(data: list[dict]) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size_kb = CACHE_PATH.stat().st_size // 1024
    print(f"  → Cache sauvegardé : {CACHE_PATH.name}  ({size_kb} KB)")


def load_cache() -> list[dict]:
    print(f"Lecture du cache : {CACHE_PATH.name}…")
    with open(CACHE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    print(f"  → {len(data)} exercices chargés")
    return data


# ── Mapping free-exercise-db → schéma local ───────────────────────────────────

def _build_muscles(ex: dict) -> str | None:
    """Fusionne muscles primaires + secondaires (deux conventions de nommage gérées)."""
    primary   = list(ex.get("muscles")           or ex.get("primaryMuscles")   or [])
    secondary = list(ex.get("musclesSecondary")  or ex.get("secondaryMuscles") or [])
    combined  = primary[:]
    for m in secondary:
        if m not in combined:
            combined.append(m)
    return json.dumps(combined, ensure_ascii=False) if combined else None


def _build_instructions(ex: dict) -> str | None:
    steps = ex.get("instructions") or []
    return "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps)) if steps else None


def _build_image_url(ex: dict) -> str | None:
    images = ex.get("images") or []
    if not images:
        return None
    return IMAGE_PREFIX + images[0].lstrip("/")


# ── Import BDD ────────────────────────────────────────────────────────────────

def import_exercises(data: list[dict]) -> tuple[int, int, int]:
    """Returns (imported, skipped, updated).
    - imported : new exercises inserted
    - skipped  : existing exercises whose image_url is already set
    - updated  : existing exercises whose image_url was NULL → now filled
    """
    init_db()
    imported = 0
    skipped  = 0
    updated  = 0

    with get_connection() as conn:
        for ex in data:
            name = (ex.get("name") or "").strip()
            if not name:
                continue

            row = conn.execute(
                "SELECT id, image_url FROM exercises WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()

            if row is None:
                # New exercise → INSERT
                img = _build_image_url(ex)
                conn.execute(
                    """INSERT INTO exercises
                       (name, muscles, image_url, gif_url, instructions, equipment, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, _build_muscles(ex), img, img,
                     _build_instructions(ex), ex.get("category") or None, "free-exercise-db"),
                )
                imported += 1
            elif not row[1]:
                # Existing exercise with NULL image_url → UPDATE with real GitHub URL
                img = _build_image_url(ex)
                if img:
                    conn.execute(
                        "UPDATE exercises SET image_url = ?, gif_url = ? WHERE id = ?",
                        (img, img, row[0]),
                    )
                    updated += 1
                else:
                    skipped += 1
            else:
                skipped += 1

        conn.commit()

    return imported, skipped, updated


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    from_cache = "--from-cache" in sys.argv

    if from_cache:
        if not CACHE_PATH.exists():
            print(f"Erreur : {CACHE_PATH} introuvable. Lance sans --from-cache d'abord.", file=sys.stderr)
            sys.exit(1)
        data = load_cache()
    else:
        data = fetch_dataset()
        save_cache(data)

    print("Import dans la base de données…")
    imported, skipped, updated = import_exercises(data)
    print(f"  → {imported} exercices importés")
    print(f"  → {updated} image_url mise à jour (exercices existants avec URL manquante)")
    print(f"  → {skipped} déjà existants (ignorés)")
    print("Terminé.")


if __name__ == "__main__":
    main()
