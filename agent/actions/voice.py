"""Appel sortant ElevenLabs (agent conversationnel + numéro Twilio). Owner : T.

Côté ElevenLabs : créer un agent dont le premier message est {{message}},
lui associer un numéro, puis remplir ELEVENLABS_AGENT_ID / ELEVENLABS_PHONE_NUMBER_ID.
Vérifier l'endpoint dans la doc ElevenLabs au premier test (10h30).
"""
from __future__ import annotations

import os

import httpx

URL = "https://api.elevenlabs.io/v1/convai/twilio/outbound-call"


def appeler(message: str, numero: str | None = None) -> str | None:
    numero = numero or os.getenv("DEMO_PHONE")
    if not numero or not os.getenv("ELEVENLABS_API_KEY"):
        print("[voice] pas de numéro ou de clé, appel simulé :", message)
        return None
    r = httpx.post(
        URL,
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        json={
            "agent_id": os.environ["ELEVENLABS_AGENT_ID"],
            "agent_phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"],
            "to_number": numero,
            "conversation_initiation_client_data": {"dynamic_variables": {"message": message}},
        },
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    return body.get("callSid") or body.get("conversation_id")
