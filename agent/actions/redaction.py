"""Drafts the voice call and the campers' SMS (both in English) with Claude, from the numbers. Owner: S.
The LLM decides nothing: it only words a decision already made by decide.py."""
from __future__ import annotations

import json

import anthropic

import config  # noqa: F401  (loads .env -> ANTHROPIC_API_KEY)

LEVELS = {"VEILLE": "watch", "ALERTE": "alert", "CRITIQUE": "critical"}

MODEL = "claude-haiku-5-5"

PROMPT = """You write flood alerts for the manager of a riverside campsite on the Ardèche river (France).
Data (do not invent anything beyond it): {data}
Reply with JSON only: {{"appel": "...", "sms": "..."}}
- "appel": in ENGLISH, 2 short spoken sentences, calm and factual: the gauging station, the rise rate in cm per hour,
  the pitches affected and the estimated time before they are reached. End with:
  "Say false alarm if this is not the case."
- "sms": in ENGLISH, evacuation SMS for campers on the affected pitches, 300 characters max."""


def _fallback(niveau, station_nom, rise_cm_h, emplacements, eta_h):
    zone = f"{emplacements[0]} to {emplacements[-1]}" if emplacements else "the low pitches"
    delay = f"in about {round(eta_h)} hours" if eta_h else "soon"
    appel = (f"{LEVELS.get(niveau, niveau).capitalize()} flood alert: the {station_nom} gauge is rising {rise_cm_h} centimetres per hour. "
             f"Pitches {zone} will be reached {delay}. Say false alarm if this is not the case.")
    sms = (f"Campsite alert: the river is rising. Please move out of pitches {zone} {delay} "
           f"and follow reception's instructions.")
    return appel, sms


def rediger(niveau, station_nom, pente_mm_h, emplacements, eta_h) -> tuple[str, str]:
    data = {
        "level": LEVELS.get(niveau, niveau),
        "station": station_nom,
        "rise_cm_per_hour": round(pente_mm_h / 10, 1),
        "pitches": emplacements,
        "eta_hours": None if eta_h is None else round(eta_h, 1),
    }
    try:
        msg = anthropic.Anthropic().messages.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": PROMPT.format(data=json.dumps(data, ensure_ascii=False))}],
        )
        txt = next(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        if "{" not in txt:
            raise ValueError(f"no JSON (stop={msg.stop_reason}): {txt[:200]!r}")
        txt = txt[txt.find("{"): txt.rfind("}") + 1]  # tolerates a ```json fence
        out = json.loads(txt)
        return out["appel"], out["sms"]
    except Exception as e:
        # no-LLM fallback: the demo must never fail because of drafting
        print("[redaction] fallback without LLM:", e)
        return _fallback(niveau, station_nom, data["rise_cm_per_hour"], emplacements, eta_h)
