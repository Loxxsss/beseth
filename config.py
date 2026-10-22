"""Connexions partagées. Toutes les valeurs viennent de .env (voir .env.example)."""
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "live")
SITE_ID = int(os.getenv("SITE_ID", "1"))
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "hydro.raw")


def _pem_path(var: str, default: str) -> str:
    """Chemin d'un certificat. Accepte aussi le contenu PEM collé dans la variable
    (pratique sur Aiven Runtime, où on ne dépose pas de fichiers) : on l'écrit
    alors dans un fichier temporaire."""
    val = os.getenv(var, default)
    if val.strip().startswith("-----BEGIN"):
        f = tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem")
        f.write(val.replace("\\n", "\n"))
        f.close()
        return f.name
    return val


def kafka_conf() -> dict:
    return {
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
        "security.protocol": "SSL",
        "ssl.ca.location": _pem_path("KAFKA_CA", "certs/ca.pem"),
        "ssl.certificate.location": _pem_path("KAFKA_CERT", "certs/service.cert"),
        "ssl.key.location": _pem_path("KAFKA_KEY", "certs/service.key"),
    }


def clickhouse():
    import clickhouse_connect

    # CLICKHOUSE_HOST accepte "host" (+ CLICKHOUSE_PORT) ou directement "host:port"
    host = os.environ["CLICKHOUSE_HOST"]
    port = os.getenv("CLICKHOUSE_PORT") or None
    if ":" in host:
        host, p = host.rsplit(":", 1)
        port = port or p
    return clickhouse_connect.get_client(
        host=host,
        port=int(port or 8443),
        username=os.environ["CLICKHOUSE_USER"],
        password=os.environ["CLICKHOUSE_PASSWORD"],
        secure=True,
    )


def postgres():
    import psycopg

    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def valkey():
    import valkey as vk

    return vk.from_url(os.environ["VALKEY_URL"])
