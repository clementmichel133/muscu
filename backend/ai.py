import json
import os

import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


DETECT_PROMPT = """\
Identifie cette machine de musculation.
Réponds UNIQUEMENT en JSON, sans texte autour :
{
  "name": "nom de la machine",
  "muscles": ["muscle1", "muscle2"],
  "tips": "conseil d'utilisation en une phrase"
}
Si ce n'est pas une machine de musculation, retourne : null"""


def _parse_data_url(image_base64: str) -> tuple[str, str]:
    """Accepte 'data:<mime>;base64,<data>' ou un base64 brut (jpeg supposé)."""
    if image_base64.startswith("data:"):
        header, data = image_base64.split(",", 1)
        media_type = header.split(";")[0].replace("data:", "")
        return media_type, data
    return "image/jpeg", image_base64


def detect_machine(image_base64: str) -> dict | None:
    """
    Envoie l'image à Claude Vision et retourne
    {"name", "muscles", "tips"} ou None si pas une machine.
    """
    media_type, data = _parse_data_url(image_base64)

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": data,
                        },
                    },
                    {"type": "text", "text": DETECT_PROMPT},
                ],
            }
        ],
    )

    text = response.content[0].text.strip()
    if text.lower() == "null":
        return None
    return json.loads(text)


WEEKLY_SYSTEM = (
    "Tu es un coach de musculation expert. "
    "Tu analyses les séances de l'utilisateur et fournis des suggestions de progression "
    "précises et motivantes. Réponds UNIQUEMENT en JSON valide, sans texte autour."
)

WEEKLY_PROMPT_TEMPLATE = """\
Voici mes séances de musculation de la semaine :
{sessions_json}

Génère des suggestions de progression en JSON :
{{
  "summary": "résumé de la semaine en 2 phrases",
  "suggestions": [
    {{
      "exercise": "nom",
      "current": "charge actuelle",
      "recommendation": "conseil précis"
    }}
  ],
  "next_week_focus": "conseil général pour la semaine prochaine"
}}"""


def weekly_suggestion(sessions: list[dict]) -> dict:
    if not sessions:
        return {
            "summary": "Aucune séance enregistrée cette semaine.",
            "suggestions": [],
            "next_week_focus": "Commencez par enregistrer vos séances pour obtenir des suggestions personnalisées.",
        }

    sessions_json = json.dumps(
        [
            {
                "exercice": s["exercise_name"],
                "date": s["date"],
                "séries": s["sets"],
                "répétitions": s["reps"],
                "poids_kg": s["weight_kg"],
                "muscles": s.get("muscles", []),
            }
            for s in sessions
        ],
        ensure_ascii=False,
        indent=2,
    )

    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=WEEKLY_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": WEEKLY_PROMPT_TEMPLATE.format(sessions_json=sessions_json),
            }
        ],
    )

    text = response.content[0].text.strip()
    # Retire les éventuels blocs ```json … ```
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)
