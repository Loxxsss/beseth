"""Connexions partagées. Toutes les valeurs viennent de .env (voir .env.example)."""
import os

from dotenv import load_dotenv

load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "live")
SITE_ID = int(os.getenv("SITE_ID", "1"))
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "hydro.raw")


def kafka_conf() -> dict:
    return {
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
        "security.protocol": "SSL",
        "ssl.ca.location": os.getenv("KAFKA_CA", "certs/ca.pem"),
        "ssl.certificate.location": os.getenv("KAFKA_CERT", "certs/service.cert"),
        "ssl.key.location": os.getenv("KAFKA_KEY", "certs/service.key"),
    }


def clickhouse():
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.getenv("CLICKHOUSE_PORT", "8443")),
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
