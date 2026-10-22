import os
import requests

URL = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"
NIVEAUX = {"VEILLE": "WATCH", "ALERTE": "ALERT", "CRITIQUE": "CRITICAL"}


def call_manager(site_nom: str, niveau: str, message: str, to_number: str | None = None) -> dict:
    """Lance l'appel au gérant. Renvoie {'ok', 'conversation_id', 'call_sid', 'error'}."""
    payload = {
        "agent_id": os.environ["ELEVENLABS_AGENT_ID"],
        "agent_phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"],
        "to_number": to_number or os.environ["DEMO_PHONE"],
        "conversation_initiation_client_data": {"dynamic_variables": {
            "site_nom": site_nom,
            "niveau": NIVEAUX.get(niveau, niveau),
            "message_alerte": message,
        }},
    }
    try:
        r = requests.post(URL, json=payload, timeout=15,
                          headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]})
        data = r.json()
        return {"ok": r.ok and data.get("success", True),
                "conversation_id": data.get("conversation_id"),
                "call_sid": data.get("callSid"),
                "error": None if r.ok else data}
    except Exception as e:  # l'appel ne doit jamais faire planter la boucle de l'agent
        return {"ok": False, "conversation_id": None, "call_sid": None, "error": str(e)}


if __name__ == "__main__":
    print(call_manager("Riverside Campsite", "ALERTE",
          "The upstream station is rising by 12 cm per hour. "
          "Pitches A1 to A8 will be flooded in about 4 hours."))
