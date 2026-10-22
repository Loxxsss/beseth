"""Rédaction du message vocal et du SMS par Claude, à partir des chiffres. Owner : S.
Le LLM ne décide rien : il met en mots une décision déjà prise par decide.py.
"""
from __future__ import annotations

import json

import anthropic

MODEL = "claude-haiku-5-5"

PROMPT = """Tu rédiges pour le gérant d'un camping en bord de rivière.
Données (ne rien inventer au-delà) : {data}
Réponds en JSON {{"appel": "...", "sms": "..."}} :
- "appel" : 2 phrases parlées, ton calme et factuel, avec la station, la vitesse de montée en cm/h,
  les emplacements touchés et le délai estimé. Termine par : "Répondez fausse alerte si ce n'est pas le cas."
- "sms" : SMS d'évacuation pour les campeurs des emplacements concernés, 300 caractères max."""


def rediger(niveau, station_nom, pente_mm_h, emplacements, eta_h) -> tuple[str, str]:
    data = {
        "niveau": niveau,
        "station": station_nom,
        "montee_cm_h": round(pente_mm_h / 10, 1),
        "emplacements": emplacements,
        "eta_h": None if eta_h is None else round(eta_h, 1),
    }
    try:
        msg = anthropic.Anthropic().messages.create(
            model=MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": PROMPT.format(data=json.dumps(data, ensure_ascii=False))}],
        )
        out = json.loads(msg.content[0].text)
        return out["appel"], out["sms"]
    except Exception:
        # repli sans LLM : la démo ne doit jamais tomber à cause de la rédaction
        zone = f"{emplacements[0]} à {emplacements[-1]}" if emplacements else "les emplacements bas"
        delai = f"dans environ {round(eta_h)} h" if eta_h else "prochainement"
        appel = (f"Alerte {niveau.lower()} : la station {station_nom} monte de {data['montee_cm_h']} cm par heure. "
                 f"Vos emplacements {zone} seront touchés {delai}. Répondez fausse alerte si ce n'est pas le cas.")
        sms = f"Camping : montée de la rivière. Merci de libérer les emplacements {zone} {delai}. Suivez les consignes de l'accueil."
        return appel, sms
