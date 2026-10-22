"""Décision déterministe (rejouable pour le backtest). Owner : S.

VEILLE   : pente > 0.5 x pente_alerte
ALERTE   : pente > pente_alerte ET au moins un emplacement avec ETA < 6 h
CRITIQUE : ETA < 2 h OU h_now > h_alerte
"""
from __future__ import annotations

from dataclasses import dataclass, field

ETA_MENACE_H = 6.0
ETA_CRITIQUE_H = 2.0


@dataclass
class Decision:
    niveau: str | None  # None | VEILLE | ALERTE | CRITIQUE
    eta_h: float | None = None
    emplacements: list[str] = field(default_factory=list)


def eta_par_emplacement(h_now, pente_mm_h, delai_h, emplacements):
    """emplacements : [(code, h_inondation_mm)] -> {code: eta_h}"""
    out = {}
    for code, h_inond in emplacements:
        if h_now >= h_inond:
            out[code] = 0.0
        elif pente_mm_h > 0:
            out[code] = (h_inond - h_now) / pente_mm_h + delai_h
    return out


def decide(h_now, pente_mm_h, delai_h, seuil, emplacements, amont=False) -> Decision:
    """seuil : dict(pente_alerte_mm_h, h_alerte_mm)
    amont=True : station en amont, ses hauteurs ne sont pas comparables aux emplacements ;
    on alerte sur la vitesse de montée, avec l'ETA = délai de propagation jusqu'au site."""
    if amont:
        tous = [c for c, _ in emplacements]
        if pente_mm_h > seuil["pente_alerte_mm_h"] or h_now > seuil["h_alerte_mm"]:
            return Decision("ALERTE", delai_h, tous)
        if pente_mm_h > 0.5 * seuil["pente_alerte_mm_h"]:
            return Decision("VEILLE", delai_h, tous)
        return Decision(None)
    etas = eta_par_emplacement(h_now, pente_mm_h, delai_h, emplacements)
    menaces = sorted((c for c, e in etas.items() if e < ETA_MENACE_H), key=etas.get)
    eta_min = min((etas[c] for c in menaces), default=None)

    if (eta_min is not None and eta_min < ETA_CRITIQUE_H) or h_now > seuil["h_alerte_mm"]:
        return Decision("CRITIQUE", eta_min, menaces)
    if pente_mm_h > seuil["pente_alerte_mm_h"] and menaces:
        return Decision("ALERTE", eta_min, menaces)
    if pente_mm_h > 0.5 * seuil["pente_alerte_mm_h"]:
        return Decision("VEILLE", eta_min, menaces)
    return Decision(None)
