"""Dédoublonnage des alertes dans Valkey. Owner : S.

Une même (site, station, niveau) ne part qu'une fois par 6 h ; une montée
ALERTE -> CRITIQUE a une clé différente donc repart. Si le module Bloom est
dispo sur Aiven Valkey, on peut passer à BF.ADD (même logique).
"""
from config import valkey

TTL_S = 6 * 3600
_client = None


def deja_envoyee(site_id: int, station: str, niveau: str) -> bool:
    global _client
    _client = _client or valkey()
    cle = f"alerte:{site_id}:{station}:{niveau}"
    return not _client.set(cle, 1, nx=True, ex=TTL_S)
