from datetime import datetime, timedelta
import os

import pandas as pd
import psycopg2
import streamlit as st
from psycopg2.extras import execute_values

from dashboard.settings import DatasetConfig, get_required_env


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "trading_data"),
        user=os.getenv("POSTGRES_USER", "dev_user"),
        password=get_required_env("POSTGRES_PASSWORD"),
    )


@st.cache_data(ttl=60)
def table_exists(table_name: str) -> bool:
    query = "SELECT to_regclass(%s) IS NOT NULL AS table_exists;"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (table_name,))
            return bool(cursor.fetchone()[0])


def dataset_tables_exist(config: DatasetConfig) -> bool:
    return table_exists(config.actual_table) and table_exists(config.prediction_table)


@st.cache_data(ttl=60)
def load_status(config: DatasetConfig) -> dict:
    query = f"""
        SELECT
            (SELECT COUNT(*) FROM {config.actual_table}) AS historical_rows,
            (SELECT MIN(timestamp) FROM {config.actual_table}) AS first_historical_timestamp,
            (SELECT MAX(timestamp) FROM {config.actual_table}) AS last_historical_timestamp,
            (SELECT COUNT(*) FROM {config.prediction_table}) AS prediction_rows,
            (SELECT MAX(prediction_date) FROM {config.prediction_table}) AS last_prediction_date,
            (
                SELECT model_name
                FROM {config.prediction_table}
                ORDER BY prediction_date DESC
                LIMIT 1
            ) AS last_model_name;
    """

    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn).iloc[0].to_dict()


@st.cache_data(ttl=60)
def load_actual_data(config: DatasetConfig, start_at: datetime, end_at: datetime) -> pd.DataFrame:
    query = f"""
        SELECT timestamp, value, source, import_date
        FROM {config.actual_table}
        WHERE timestamp >= %s
          AND timestamp <= %s
        ORDER BY timestamp;
    """

    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=(start_at, end_at))


@st.cache_data(ttl=60)
def load_predictions(config: DatasetConfig, start_at: datetime, end_at: datetime) -> pd.DataFrame:
    query = f"""
        SELECT timestamp, predicted_value, model_name, horizon, prediction_date
        FROM {config.prediction_table}
        WHERE timestamp >= %s
          AND timestamp <= %s
        ORDER BY timestamp;
    """

    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=(start_at, end_at))


def load_latest_context(config: DatasetConfig, context_length: int) -> tuple[list[float], datetime]:
    query = f"""
        SELECT timestamp, value
        FROM {config.actual_table}
        ORDER BY timestamp DESC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (context_length,))
            rows = cursor.fetchall()

    if len(rows) < context_length:
        raise RuntimeError(
            f"Pas assez de donnees {config.menu_label.lower()}: {len(rows)} lignes trouvees, "
            f"{context_length} requises."
        )

    rows = list(reversed(rows))
    context = [float(row[1]) for row in rows]
    latest_timestamp = rows[-1][0]

    return context, latest_timestamp


def insert_predictions(config: DatasetConfig, api_response: dict, latest_timestamp: datetime) -> int:
    rows = []
    for point in api_response["predictions"]:
        step = int(point["step"])
        rows.append(
            (
                latest_timestamp + timedelta(hours=step),
                float(point["predicted_value"]),
                api_response["model_name"],
                f"H+{step}",
            )
        )

    query = f"""
        INSERT INTO {config.prediction_table} (timestamp, predicted_value, model_name, horizon)
        VALUES %s
        ON CONFLICT (timestamp, model_name, horizon)
        DO UPDATE SET
            predicted_value = EXCLUDED.predicted_value,
            prediction_date = NOW();
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            execute_values(cursor, query, rows)

    st.cache_data.clear()
    return len(rows)
