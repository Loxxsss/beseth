"""Annulation des sorties canoë de l'après-midi (niveau CRITIQUE). Owner : S."""
from config import postgres


def annuler_sorties(site_id: int) -> int:
    with postgres() as conn:
        cur = conn.execute(
            """UPDATE sorties SET statut='annulee'
               WHERE site_id=%s AND statut='prevue'
                 AND debut BETWEEN now() AND date_trunc('day', now()) + interval '1 day'""",
            (site_id,),
        )
    return cur.rowcount
