"""Rédaction du message vocal (anglais, agent ElevenLabs « Beseth ») et du SMS campeurs (français)
par Claude, à partir des chiffres. Owner : S.
Le LLM ne décide rien : il met en mots une décision déjà prise par decide.py.
"""
from __future__ import annotations

import json

import anthropic

MODEL = "claude-haiku-5-5"

PROMPT = """You write flood alerts for the manager of a riverside campsite on the Ardèche river (France).
Data (do not invent anything beyond it): {data}
Reply with JSON only: {{"appel": "...", "sms": "..."}}
- "appel": in ENGLISH, 2 short spoken sentences, calm and factual: the gauging station, the rise rate in cm per hour,
  the pitches affected and the estimated time before they are reached. End with:
  "Say false alarm if this is not the case."
- "sms": in FRENCH, evacuation SMS for campers on the affected pitches, 300 characters max."""


def _repli(niveau, station_nom, montee_cm_h, emplacements, eta_h):
    zone = f"{emplacements[0]} to {emplacements[-1]}" if emplacements else "the low pitches"
    zone_fr = f"{emplacements[0]} à {emplacements[-1]}" if emplacements else "les emplacements bas"
    delai = f"in about {round(eta_h)} hours" if eta_h else "soon"
    delai_fr = f"dans environ {round(eta_h)} h" if eta_h else "prochainement"
    appel = (f"{niveau.capitalize()} flood alert: the {station_nom} gauge is rising {montee_cm_h} centimetres per hour. "
             f"Pitches {zone} will be reached {delai}. Say false alarm if this is not the case.")
    sms = (f"Camping : montée de la rivière. Merci de libérer les emplacements {zone_fr} {delai_fr}. "
           f"Suivez les consignes de l'accueil.")
    return appel, sms


def rediger(niveau, station_nom, pente_mm_h, emplacements, eta_h) -> tuple[str, str]:
    data = {
        "level": niveau,
        "station": station_nom,
        "rise_cm_per_hour": round(pente_mm_h / 10, 1),
        "pitches": emplacements,
        "eta_hours": None if eta_h is None else round(eta_h, 1),
    }
    try:
        msg = anthropic.Anthropic().messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": PROMPT.format(data=json.dumps(data, ensure_ascii=False))}],
        )
        txt = msg.content[0].text.strip()
        txt = txt[txt.find("{"): txt.rfind("}") + 1]  # tolère un éventuel ```json
        out = json.loads(txt)
        return out["appel"], out["sms"]
    except Exception as e:
        # repli sans LLM : la démo ne doit jamais tomber à cause de la rédaction
        print("[redaction] repli sans LLM :", e)
        return _repli(niveau, station_nom, data["rise_cm_per_hour"], emplacements, eta_h)
