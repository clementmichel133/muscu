# Suivi Musculation — Spec

## Ce que l'app fait
- Saisir une séance : exercice + séries + charges + reps
- Ajouter un exercice via :
  - Saisie manuelle du nom
  - Description en texte libre (ex: "développé couché prise large, descente lente 3s")
  - Photo de la machine → Claude détecte automatiquement le nom + muscles ciblés
- Voir l'historique par exercice
- Voir la progression (graphe simple)
- Résumé hebdomadaire + suggestions de progression générées par Claude

## Ce que l'app ne fait PAS (MVP)
- Pas de compte utilisateur / auth
- Pas d'app mobile native
- Pas de base d'exercices prédéfinie (saisie libre au départ)

## Stack
- Backend  : FastAPI + SQLite
- Frontend : HTML/JS vanilla, responsive mobile-first, Tailwind CSS
- IA       : Anthropic API (claude-sonnet-4-6)
  - Vision : détection machine depuis photo (multimodal)
  - Text   : suggestions hebdo de progression

## UI/UX — ui-ux-pro-max-skill
Installer le skill avant tout développement frontend :
```bash
npm install -g uipro-cli
cd /path/to/muscu
uipro init --ai claude
```
Stack cible : **html-tailwind**
Style cible : **dark mode**, boutons larges (usage téléphone en salle)
Consulter `.claude/skills/ui-ux-pro-max/SKILL.md` avant chaque composant UI.

## Utilisateur
- Moi seul, sur téléphone via navigateur (pas besoin d'auth)

---

## Schéma base de données

```sql
exercises (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  description TEXT,          -- description libre en phrase
  muscles     TEXT,          -- JSON array ex: ["pectoraux", "triceps"]
  photo_path  TEXT           -- chemin vers la photo de la machine
)

sessions (
  id          INTEGER PRIMARY KEY,
  date        TEXT NOT NULL, -- ISO format YYYY-MM-DD
  exercise_id INTEGER REFERENCES exercises(id),
  sets        INTEGER,
  reps        INTEGER,
  weight_kg   REAL
)
```

---

## Endpoints API

| Méthode | Route                        | Description                          |
|---------|------------------------------|--------------------------------------|
| GET     | /exercises                   | Liste tous les exercices             |
| POST    | /exercises                   | Créer un exercice (texte)            |
| POST    | /exercises/detect            | Créer un exercice depuis une photo   |
| POST    | /sessions                    | Enregistrer une séance               |
| GET     | /sessions/{exercise_name}    | Historique d'un exercice             |
| GET     | /weekly-summary              | Données + suggestions Claude         |

---

## Feature : détection machine par photo

Flux :
1. Utilisateur prend une photo dans l'app (input type=file + capture)
2. Frontend envoie l'image en base64 au backend → POST /exercises/detect
3. Backend appelle Claude API (multimodal) avec ce prompt :

```
Identifie cette machine de musculation.
Réponds UNIQUEMENT en JSON, sans texte autour :
{
  "name": "nom de la machine",
  "muscles": ["muscle1", "muscle2"],
  "tips": "conseil d'utilisation en une phrase"
}
Si ce n'est pas une machine de musculation, retourne : null
```

4. Claude retourne le JSON → backend pré-remplit le formulaire
5. Utilisateur confirme ou corrige avant sauvegarde

Modèle : `claude-sonnet-4-6`
Coût estimé : ~0.002€ par photo (négligeable)

---

## Feature : suggestions hebdomadaires

Flux :
1. GET /weekly-summary appelle `weekly_suggestion()` dans ai.py
2. Récupère toutes les séances de la semaine depuis SQLite
3. Envoie à Claude le contexte formaté + prompt :

```
Voici mes séances de musculation de la semaine :
{sessions_json}

Génère des suggestions de progression en JSON :
{
  "summary": "résumé de la semaine en 2 phrases",
  "suggestions": [
    {
      "exercise": "nom",
      "current": "charge actuelle",
      "recommendation": "conseil précis"
    }
  ],
  "next_week_focus": "conseil général pour la semaine prochaine"
}
```

---

## Structure du projet

```
muscu/
├── SPEC.md                  ← ce fichier
├── CLAUDE.md                ← généré par uipro init --ai claude
├── .claude/
│   └── skills/
│       └── ui-ux-pro-max/   ← généré par uipro init
├── backend/
│   ├── main.py              ← FastAPI + routes
│   ├── database.py          ← SQLite + CRUD
│   └── ai.py                ← Anthropic API (vision + texte)
├── frontend/
│   ├── index.html           ← page principale (saisie séance)
│   ├── exercises.html       ← liste + ajout exercices
│   ├── history.html         ← historique + graphes
│   ├── weekly.html          ← résumé + suggestions
│   └── app.js               ← fetch API calls
├── requirements.txt
└── .env                     ← ANTHROPIC_API_KEY (ne pas committer)
```

---

## Ordre de développement (sprints)

**Sprint 1 — BDD (1h)**
Créer `database.py` avec SQLite, tables exercises + sessions, fonctions CRUD.

**Sprint 2 — Backend API (1h)**
Créer `main.py` FastAPI avec tous les endpoints. Tester sur /docs.

**Sprint 3 — Feature détection photo (1h)**
Créer `ai.py` avec `detect_machine(image_path)`. Brancher sur POST /exercises/detect.

**Sprint 4 — Frontend mobile (2h)**
HTML/JS vanilla + Tailwind, dark mode, boutons larges.
Consulter ui-ux-pro-max SKILL.md avant de coder.

**Sprint 5 — Suggestions hebdo IA (1h)**
Ajouter `weekly_suggestion()` dans ai.py. Brancher sur GET /weekly-summary.

**Total estimé : 6h**

---

## Règles Claude Code

- Lire SPEC.md avant de commencer
- Traiter un sprint à la fois — attendre validation avant de continuer
- Consulter `.claude/skills/ui-ux-pro-max/SKILL.md` avant tout composant UI
- Ne jamais committer le fichier .env
- Tester chaque endpoint sur /docs avant de passer au frontend
