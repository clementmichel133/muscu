"""
Insère des données d'entraînement historiques (Sep 2025 → juin 2026).
Usage : python backend/seed_data.py
"""

import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

DB_PATH = Path(__file__).parent.parent / "muscu.db"

PHASE1_START = date(2025, 9, 1)
PHASE1_END   = date(2025, 12, 31)
PHASE2_START = date(2026, 1, 1)
TODAY        = date(2026, 6, 1)

# Lundis des semaines sans entraînement (vacances / maladie)
SKIP_WEEKS = {
    date(2025, 10, 13),  # maladie
    date(2025, 11, 10),  # maladie
    date(2025, 12, 22),  # vacances Noël
    date(2025, 12, 29),  # vacances Noël
    date(2026, 1,  5),   # fin vacances Noël
    date(2026, 2, 16),   # vacances d'hiver
    date(2026, 3, 30),   # maladie
    date(2026, 5, 11),   # maladie
}

EXERCISES = {
    "Pec": [
        {"name": "Développé couché",    "muscles": ["Pectoraux", "Triceps", "Deltoïde antérieur"]},
        {"name": "Écarté poulie",        "muscles": ["Pectoraux"]},
        {"name": "Dips",                 "muscles": ["Pectoraux", "Triceps"]},
    ],
    "Biceps": [
        {"name": "Curl barre",           "muscles": ["Biceps"]},
        {"name": "Curl incliné",         "muscles": ["Biceps"]},
        {"name": "Marteau",              "muscles": ["Biceps", "Brachio-radial"]},
    ],
    "Dos": [
        {"name": "Tractions",            "muscles": ["Grand dorsal", "Biceps"]},
        {"name": "Rowing barre",         "muscles": ["Grand dorsal", "Rhomboïdes"]},
        {"name": "Tirage poulie",        "muscles": ["Grand dorsal"]},
    ],
    "Triceps": [
        {"name": "Pushdown câble",       "muscles": ["Triceps"]},
        {"name": "Barre front",          "muscles": ["Triceps"]},
        {"name": "Extensions haltère",   "muscles": ["Triceps"]},
    ],
    "Épaules": [
        {"name": "Développé militaire",  "muscles": ["Deltoïdes", "Triceps"]},
        {"name": "Élévations latérales", "muscles": ["Deltoïde latéral"]},
        {"name": "Oiseau",               "muscles": ["Deltoïde postérieur"]},
    ],
    "Mollets": [
        {"name": "Mollets debout",       "muscles": ["Gastrocnémien"]},
        {"name": "Mollets assis",        "muscles": ["Soléaire"]},
    ],
    "Jambes": [
        {"name": "Squat",                "muscles": ["Quadriceps", "Fessiers", "Ischio-jambiers"]},
        {"name": "Leg press",            "muscles": ["Quadriceps", "Fessiers"]},
        {"name": "Fentes",               "muscles": ["Quadriceps", "Fessiers"]},
        {"name": "Leg curl",             "muscles": ["Ischio-jambiers"]},
    ],
}

# w0 = poids initial (kg), gain = gain par séance (kg), sets, reps = fourchette
PROG = {
    "Développé couché":    {"w0": 40.0,  "gain": 1.25, "sets": 4, "reps": (8,  10)},
    "Écarté poulie":        {"w0": 12.0,  "gain": 0.50, "sets": 3, "reps": (12, 15)},
    "Dips":                 {"w0":  0.0,  "gain": 1.25, "sets": 3, "reps": (8,  10)},
    "Curl barre":           {"w0": 25.0,  "gain": 0.75, "sets": 4, "reps": (8,  10)},
    "Curl incliné":         {"w0":  8.0,  "gain": 0.50, "sets": 3, "reps": (10, 12)},
    "Marteau":              {"w0": 10.0,  "gain": 0.50, "sets": 3, "reps": (10, 12)},
    "Tractions":            {"w0":  0.0,  "gain": 1.25, "sets": 4, "reps": (5,   8)},
    "Rowing barre":         {"w0": 50.0,  "gain": 1.25, "sets": 4, "reps": (8,  10)},
    "Tirage poulie":        {"w0": 40.0,  "gain": 1.00, "sets": 3, "reps": (10, 12)},
    "Pushdown câble":       {"w0": 20.0,  "gain": 0.75, "sets": 3, "reps": (12, 15)},
    "Barre front":          {"w0": 25.0,  "gain": 0.75, "sets": 3, "reps": (8,  10)},
    "Extensions haltère":   {"w0": 12.0,  "gain": 0.50, "sets": 3, "reps": (10, 12)},
    "Développé militaire":  {"w0": 35.0,  "gain": 1.00, "sets": 4, "reps": (8,  10)},
    "Élévations latérales": {"w0":  8.0,  "gain": 0.25, "sets": 3, "reps": (12, 15)},
    "Oiseau":               {"w0":  7.0,  "gain": 0.25, "sets": 3, "reps": (12, 15)},
    "Mollets debout":       {"w0": 60.0,  "gain": 2.50, "sets": 4, "reps": (15, 20)},
    "Mollets assis":        {"w0": 40.0,  "gain": 1.50, "sets": 3, "reps": (15, 20)},
    "Squat":                {"w0": 50.0,  "gain": 2.00, "sets": 4, "reps": (6,   8)},
    "Leg press":            {"w0": 90.0,  "gain": 3.00, "sets": 4, "reps": (10, 12)},
    "Fentes":               {"w0": 15.0,  "gain": 0.75, "sets": 3, "reps": (10, 12)},
    "Leg curl":             {"w0": 35.0,  "gain": 1.25, "sets": 3, "reps": (10, 12)},
}

# Phase 1 : alternance Pec+Triceps / Jambes
PHASE1_TYPES = [["Pec", "Triceps"], ["Jambes"]]

# Phase 2 : rotation sur 4 jours
PHASE2_ROTATION = [
    ["Pec", "Biceps"],
    ["Dos", "Triceps"],
    ["Épaules", "Mollets"],
    ["Jambes"],
]


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def round_2_5(w: float) -> float:
    return max(0.0, round(w / 2.5) * 2.5)


def weight_with_noise(name: str, count: int) -> float:
    p = PROG[name]
    w = p["w0"] + count * p["gain"]
    if random.random() < 0.10:
        w += random.choice([-2.5, 2.5])
    return round_2_5(w)


def weight_clean(name: str, count: int) -> float:
    p = PROG[name]
    return round_2_5(p["w0"] + count * p["gain"])


def main():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM exercises")
    conn.commit()

    # ── Exercices ─────────────────────────────────────────────────────────────
    ex_ids: dict[str, int] = {}
    for exercises in EXERCISES.values():
        for ex in exercises:
            cur = conn.execute(
                "INSERT INTO exercises (name, muscles) VALUES (?, ?)",
                (ex["name"], json.dumps(ex["muscles"])),
            )
            ex_ids[ex["name"]] = cur.lastrowid
    conn.commit()

    ex_counts: dict[str, int] = {name: 0 for name in ex_ids}
    rows: list[tuple] = []

    # ── Phase 1 : Sep – Déc 2025 (1-2x/sem, débutant) ────────────────────────
    p1_idx = 0
    monday = get_monday(PHASE1_START)
    while monday <= PHASE1_END:
        if monday not in SKIP_WEEKS:
            n = random.choices([1, 2], weights=[0.4, 0.6])[0]
            for offset in sorted(random.sample(range(6), n)):
                d = monday + timedelta(days=offset)
                if not (PHASE1_START <= d <= PHASE1_END):
                    continue
                for group in PHASE1_TYPES[p1_idx % 2]:
                    for ex in EXERCISES[group]:
                        name = ex["name"]
                        p = PROG[name]
                        rows.append((
                            d.isoformat(),
                            ex_ids[name],
                            p["sets"],
                            random.randint(*p["reps"]),
                            weight_with_noise(name, ex_counts[name]),
                        ))
                        ex_counts[name] += 1
                p1_idx += 1
        monday += timedelta(weeks=1)

    # ── Phase 2 : Jan 2026 → aujourd'hui (4x/sem, rotation) ──────────────────
    p2_idx = 0
    monday = get_monday(PHASE2_START)
    while monday <= TODAY:
        if monday not in SKIP_WEEKS:
            for offset in sorted(random.sample(range(6), 4)):
                d = monday + timedelta(days=offset)
                if not (PHASE2_START <= d <= TODAY):
                    continue
                for group in PHASE2_ROTATION[p2_idx % 4]:
                    for ex in EXERCISES[group]:
                        name = ex["name"]
                        p = PROG[name]
                        rows.append((
                            d.isoformat(),
                            ex_ids[name],
                            p["sets"],
                            random.randint(*p["reps"]),
                            weight_with_noise(name, ex_counts[name]),
                        ))
                        ex_counts[name] += 1
                p2_idx += 1
        monday += timedelta(weeks=1)

    rows.sort(key=lambda r: r[0])
    conn.executemany(
        "INSERT INTO sessions (date, exercise_id, sets, reps, weight_kg) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    # ── Résumé ────────────────────────────────────────────────────────────────
    print(f"\nSeed OK — {len(ex_ids)} exercices, {len(rows)} lignes de séances.\n")
    print(f"  {'Exercice':<26} {'Séances':>7}  {'Départ':>8}  {'Arrivée':>8}")
    print("  " + "-" * 58)
    for group, exercises in EXERCISES.items():
        print(f"  [{group}]")
        for ex in exercises:
            name = ex["name"]
            cnt  = ex_counts[name]
            w0   = PROG[name]["w0"]
            wf   = weight_clean(name, cnt)
            print(f"    {name:<24} {cnt:>7}   {w0:>6.1f}kg   {wf:>6.1f}kg")
    print()


if __name__ == "__main__":
    main()
