"""Boucle de l'agent : toutes les 2 min (20 s en replay). Owner : S."""
import time

from agent import dedup, memory
from agent.actions import planning, voice
from agent.actions.redaction import rediger
from agent.decide import decide
from agent.trend import tendances
from config import DEMO_MODE, SITE_ID


def tour(site_id: int = SITE_ID):
    ctx = memory.contexte_site(site_id)
    for code, t in tendances(list(ctx["stations"])).items():
        seuil = ctx["seuils"].get(code)
        if not seuil:
            continue
        d = decide(t.h_now, t.pente_mm_h, ctx["stations"][code]["delai_h"], seuil, ctx["emplacements"])
        print(f"{code} h={t.h_now:.0f}mm pente={t.pente_mm_h:.0f}mm/h -> {d.niveau} {d.emplacements}")
        if d.niveau in (None, "VEILLE"):
            continue  # VEILLE = statut orange sur la carte, rien d'envoyé
        if dedup.deja_envoyee(site_id, code, d.niveau):
            continue
        appel, sms = rediger(d.niveau, code, t.pente_mm_h, d.emplacements, d.eta_h)
        call_id = voice.appeler(appel, ctx["tel_gerant"])
        if d.niveau == "CRITIQUE":
            planning.annuler_sorties(site_id)
        memory.enregistrer_alerte(site_id, code, d, t, appel, sms, call_id)


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
