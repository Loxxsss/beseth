"""Boucle de l'agent : toutes les 2 min (20 s en replay). Owner : S."""
from __future__ import annotations

import json
import time

from agent import dedup, memory, trace
from agent.actions import planning, voice
from agent.actions.redaction import rediger
from agent.decide import decide
from agent.trend import tendances
from config import DEMO_MODE, SITE_ID


NOMS = {"V501401001": "Vogüé", "V505401001": "Vallon-Pont-d'Arc"}  # nom lu à l'oral plutôt que le code


def appeler(site_nom: str, niveau: str, message: str):
    """Passe par voice.call_manager (variables site_nom / niveau / message_alerte de l'agent ElevenLabs).
    Ne fait jamais tomber la boucle : un appel raté est journalisé, l'alerte est quand même enregistrée."""
    try:
        if hasattr(voice, "call_manager"):
            res = voice.call_manager(site_nom, niveau, message)
        else:  # voice.py de T pas encore poussé : ancienne fonction
            res = voice.appeler(message)
    except Exception as e:
        print("[voice] appel échoué :", e)
        return None
    if isinstance(res, dict):
        res = next((res[k] for k in ("callSid", "call_sid", "conversation_id", "call_id", "sid", "id") if res.get(k)), None) \
            or json.dumps(res)[:200]
    return None if res is None else str(res)


def tour(site_id: int = SITE_ID):
    ctx = memory.contexte_site(site_id)
    for code, t in tendances(list(ctx["stations"])).items():
        seuil = ctx["seuils"].get(code)
        if not seuil:
            continue
        st = ctx["stations"][code]
        d = decide(t.h_now, t.pente_mm_h, st["delai_h"], seuil, ctx["emplacements"], amont=st["role"] == "amont")
        print(f"{code} h={t.h_now:.0f}mm pente={t.pente_mm_h:.0f}mm/h -> {d.niveau} {d.emplacements}")
        if d.niveau in (None, "VEILLE"):
            continue  # VEILLE = statut orange sur la carte, rien d'envoyé
        if dedup.deja_envoyee(site_id, code, d.niveau):
            continue
        tr = trace.construire(code, st["role"], st["delai_h"], t, seuil, d)
        appel, sms = rediger(d.niveau, NOMS.get(code, code), t.pente_mm_h, d.emplacements, d.eta_h)
        call_id = appeler(ctx["site_nom"], d.niveau, appel)
        if d.niveau == "CRITIQUE":
            tr["sorties_annulees"] = planning.annuler_sorties(site_id)
        memory.enregistrer_alerte(site_id, code, d, t, appel, sms, call_id, tr)


def main():
    pause = 20 if DEMO_MODE == "replay" else 120
    while True:
        try:
            tour()
        except Exception as e:  # la boucle ne doit jamais mourir en démo
            print("[loop] erreur :", e)
        time.sleep(pause)


if __name__ == "__main__":
    main()
