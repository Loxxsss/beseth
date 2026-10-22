"""Statut affiché + trace du raisonnement (les chiffres derrière chaque décision). Owner : S.
Partagé par agent/loop.py (enregistré dans alertes.trace) et api/main.py (/stations).
"""
from __future__ import annotations

PERIMEE_MIN = 30  # dernière mesure live plus vieille que ça -> statut "perimee"


def statut(decision, tendance) -> str:
    """normal | veille | alerte | critique | perimee"""
    age = tendance.age_min()
    if tendance.source != "replay" and age is not None and age > PERIMEE_MIN:
        return "perimee"
    return {None: "normal", "VEILLE": "veille", "ALERTE": "alerte", "CRITIQUE": "critique"}[decision.niveau]


def construire(code, role, delai_h, tendance, seuil, decision) -> dict:
    age = tendance.age_min()
    r = lambda x, n=0: None if x is None else round(x, n)
    return {
        "station": code,
        "role": role,
        "h_now_mm": r(tendance.h_now),
        "pente_1h_mm_h": r(tendance.pente_1h),
        "pente_3h_mm_h": r(tendance.pente_3h),
        "pente_retenue_mm_h": r(tendance.pente_mm_h),
        "seuil": {
            "pente_alerte_mm_h": seuil["pente_alerte_mm_h"],
            "h_alerte_mm": seuil["h_alerte_mm"],
            "version": seuil.get("version", 1),
        },
        "delai_propagation_h": delai_h,
        "eta_h": r(decision.eta_h, 1),
        "emplacements_menaces": decision.emplacements,
        "niveau": decision.niveau,
        "derniere_mesure": tendance.derniere_mesure.isoformat() if tendance.derniere_mesure else None,
        "age_donnee_min": r(age, 1),
        "source": tendance.source,
    }
