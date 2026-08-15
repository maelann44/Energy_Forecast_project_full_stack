import argparse
import logging
import os
from datetime import timedelta
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "prediction_batch.log"


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


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "trading_data"),
        user=os.getenv("POSTGRES_USER", "dev_user"),
        password=get_required_env("POSTGRES_PASSWORD"),
    )


def load_latest_context(context_length: int) -> tuple[list[float], object]:
    query = """
        SELECT timestamp, value
        FROM historical_data
        ORDER BY timestamp DESC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (context_length,))
            rows = cursor.fetchall()

    if len(rows) < context_length:
        raise RuntimeError(
            f"Pas assez de donnees historiques: {len(rows)} lignes trouvees, "
            f"{context_length} requises."
        )

    rows = list(reversed(rows))
    latest_timestamp = rows[-1][0]
    context = [float(row[1]) for row in rows]

    return context, latest_timestamp


def call_prediction_api(
    api_url: str,
    context: list[float],
    prediction_length: int,
) -> dict:
    payload = {
        "context": context,
        "prediction_length": prediction_length,
        "quantiles": [0.1, 0.5, 0.9],
    }

    try:
        response = requests.post(api_url, json=payload, timeout=180)
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise RuntimeError(
            "Impossible de joindre l'API FastAPI. Lance d'abord: "
            "py -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"
        ) from exc
    except requests.HTTPError as exc:
        raise RuntimeError(
            f"Erreur API prediction {response.status_code}: {response.text}"
        ) from exc

    return response.json()


def insert_predictions(api_response: dict, latest_timestamp, prediction_length: int) -> int:
    model_name = api_response["model_name"]
    prediction_points = api_response["predictions"]

    rows = []
    for point in prediction_points:
        step = int(point["step"])
        predicted_timestamp = latest_timestamp + timedelta(hours=step)
        rows.append(
            (
                predicted_timestamp,
                float(point["predicted_value"]),
                model_name,
                f"H+{step}",
            )
        )

    if len(rows) != prediction_length:
        raise RuntimeError("La reponse API ne contient pas le bon nombre de predictions.")

    query = """
        INSERT INTO predictions (timestamp, predicted_value, model_name, horizon)
        VALUES %s
        ON CONFLICT (timestamp, model_name, horizon)
        DO UPDATE SET
            predicted_value = EXCLUDED.predicted_value,
            prediction_date = NOW();
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            execute_values(cursor, query, rows)

    return len(rows)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lance une prediction batch via FastAPI et stocke le resultat dans PostgreSQL."
    )
    parser.add_argument("--api-url", default="http://localhost:8000/predict")
    parser.add_argument("--context-length", type=int, default=168)
    parser.add_argument("--prediction-length", type=int, default=24)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Appelle l'API mais n'insere rien dans PostgreSQL.",
    )
    return parser


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    setup_logging()

    args = build_arg_parser().parse_args()

    logging.info("Chargement des %s dernieres valeurs historiques", args.context_length)
    context, latest_timestamp = load_latest_context(args.context_length)
    logging.info("Dernier timestamp historique: %s", latest_timestamp)

    logging.info("Appel API prediction: %s", args.api_url)
    api_response = call_prediction_api(args.api_url, context, args.prediction_length)

    if args.dry_run:
        logging.info("Mode dry-run actif: aucune insertion dans predictions.")
        logging.info("Premiere prediction: %s", api_response["predictions"][0])
        return

    inserted_count = insert_predictions(api_response, latest_timestamp, args.prediction_length)
    logging.info("Predictions inserees: %s", inserted_count)


if __name__ == "__main__":
    main()
