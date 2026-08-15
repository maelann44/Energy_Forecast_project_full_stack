import argparse
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "ingestion.log"

RTE_TOKEN_URL = "https://digital.iservices.rte-france.com/token/oauth/"
RTE_CONSUMPTION_URL = "https://digital.iservices.rte-france.com/open_api/consumption/v1/short_term"
PARIS_TZ = ZoneInfo("Europe/Paris")


def format_rte_datetime(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def floor_to_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante: {name}")
    return value


def get_rte_token() -> str:
    client_id = get_required_env("RTE_CLIENT_ID")
    client_secret = get_required_env("RTE_CLIENT_SECRET")

    response = requests.post(
        RTE_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=30,
    )
    response.raise_for_status()

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("La reponse RTE ne contient pas de access_token")

    return token


def fetch_consumption(token: str, start_date: datetime, end_date: datetime) -> list[dict]:
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "type": "REALISED",
        "start_date": format_rte_datetime(start_date),
        "end_date": format_rte_datetime(end_date),
    }

    response = requests.get(
        RTE_CONSUMPTION_URL,
        headers=headers,
        params=params,
        timeout=60,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise RuntimeError(
            "Erreur API RTE "
            f"{response.status_code} pour start_date={params['start_date']} "
            f"et end_date={params['end_date']}. Reponse: {response.text}"
        ) from exc

    payload = response.json()
    short_term = payload.get("short_term", [])
    if not short_term:
        return []

    return short_term[0].get("values", [])


def clean_consumption(raw_values: list[dict], min_points_per_hour: int) -> pd.DataFrame:
    if not raw_values:
        return pd.DataFrame(columns=["timestamp", "value", "source"])

    df = pd.DataFrame(raw_values)
    df = df.rename(columns={"start_date": "timestamp"})
    df = df[["timestamp", "value"]].copy()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["timestamp", "value"])
    df = df[df["value"] >= 0]

    df["hour"] = df["timestamp"].dt.floor("h")
    hourly = (
        df.groupby("hour", as_index=False)
        .agg(value=("value", "mean"), points_count=("value", "size"))
    )

    hourly = hourly[hourly["points_count"] >= min_points_per_hour]
    hourly = hourly.rename(columns={"hour": "timestamp"})
    hourly["source"] = "RTE"

    return hourly[["timestamp", "value", "source"]]


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "trading_data"),
        user=os.getenv("POSTGRES_USER", "dev_user"),
        password=get_required_env("POSTGRES_PASSWORD"),
    )


def insert_historical_data(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    rows = [
        (row.timestamp.to_pydatetime(), float(row.value), row.source)
        for row in df.itertuples(index=False)
    ]

    query = """
        INSERT INTO historical_data (timestamp, value, source)
        VALUES %s
        ON CONFLICT (timestamp, source)
        DO UPDATE SET
            value = EXCLUDED.value,
            import_date = NOW();
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            execute_values(cursor, query, rows)

    return len(rows)


def parse_date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PARIS_TZ)
    return parsed.replace(microsecond=0)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recupere les donnees de consommation RTE et les insere dans PostgreSQL."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Nombre d'heures recentes a recuperer si start/end ne sont pas fournis.",
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        help="Date de debut, exemple: 2024-10-01T00:00:00+02:00",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Date de fin, exemple: 2024-10-02T00:00:00+02:00",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Recupere et nettoie les donnees sans insertion en base.",
    )
    parser.add_argument(
        "--min-points-per-hour",
        type=int,
        default=4,
        help="Nombre minimum de points requis pour garder une heure complete.",
    )
    return parser


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    setup_logging()

    args = build_arg_parser().parse_args()

    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    elif not args.start_date and not args.end_date:
        end_date = floor_to_hour(datetime.now(PARIS_TZ))
        start_date = end_date - timedelta(hours=args.hours)
    else:
        raise RuntimeError("Il faut fournir start-date et end-date ensemble.")

    if start_date >= end_date:
        raise RuntimeError("start-date doit etre strictement inferieure a end-date.")

    logging.info(
        "Debut ingestion RTE: %s -> %s",
        format_rte_datetime(start_date),
        format_rte_datetime(end_date),
    )

    token = get_rte_token()
    raw_values = fetch_consumption(token, start_date, end_date)
    logging.info("Points bruts recuperes: %s", len(raw_values))

    cleaned = clean_consumption(raw_values, args.min_points_per_hour)
    logging.info("Lignes horaires apres nettoyage: %s", len(cleaned))

    if args.dry_run:
        logging.info("Mode dry-run actif: aucune insertion PostgreSQL.")
        print(cleaned.head(10))
        return

    inserted_count = insert_historical_data(cleaned)
    logging.info("Lignes inserees ou mises a jour dans historical_data: %s", inserted_count)
    logging.info("Fin ingestion RTE")


if __name__ == "__main__":
    main()
