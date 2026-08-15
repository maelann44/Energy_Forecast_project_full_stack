from datetime import date, datetime, time, timedelta
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import psycopg2
import requests
import streamlit as st
from dotenv import load_dotenv
from psycopg2.extras import execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_FASTAPI_URL = os.getenv("PREDICTION_API_URL", "http://localhost:8000/predict")


st.set_page_config(
    page_title="Electricity Forecast Dashboard",
    layout="wide",
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


@st.cache_data(ttl=60)
def load_status() -> dict:
    query = """
        SELECT
            (SELECT COUNT(*) FROM historical_data) AS historical_rows,
            (SELECT MIN(timestamp) FROM historical_data) AS first_historical_timestamp,
            (SELECT MAX(timestamp) FROM historical_data) AS last_historical_timestamp,
            (SELECT COUNT(*) FROM predictions) AS prediction_rows,
            (SELECT MAX(prediction_date) FROM predictions) AS last_prediction_date,
            (SELECT model_name FROM predictions ORDER BY prediction_date DESC LIMIT 1) AS last_model_name;
    """

    with get_db_connection() as conn:
        status = pd.read_sql_query(query, conn).iloc[0].to_dict()

    return status


@st.cache_data(ttl=60)
def load_historical_data(start_at: datetime, end_at: datetime) -> pd.DataFrame:
    query = """
        SELECT timestamp, value, source, import_date
        FROM historical_data
        WHERE timestamp >= %s
          AND timestamp <= %s
        ORDER BY timestamp;
    """

    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=(start_at, end_at))


@st.cache_data(ttl=60)
def load_predictions(start_at: datetime, end_at: datetime) -> pd.DataFrame:
    query = """
        SELECT timestamp, predicted_value, model_name, horizon, prediction_date
        FROM predictions
        WHERE timestamp >= %s
          AND timestamp <= %s
        ORDER BY timestamp;
    """

    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=(start_at, end_at))


def load_latest_context(context_length: int) -> tuple[list[float], datetime]:
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
    context = [float(row[1]) for row in rows]
    latest_timestamp = rows[-1][0]

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

    response = requests.post(api_url, json=payload, timeout=180)
    response.raise_for_status()

    return response.json()


def insert_predictions(api_response: dict, latest_timestamp: datetime) -> int:
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

    st.cache_data.clear()
    return len(rows)


def build_forecast_figure(historical_df: pd.DataFrame, predictions_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    if not historical_df.empty:
        fig.add_trace(
            go.Scatter(
                x=historical_df["timestamp"],
                y=historical_df["value"],
                mode="lines",
                name="Consommation reelle",
                line={"color": "#2563eb", "width": 2},
            )
        )

    if not predictions_df.empty:
        fig.add_trace(
            go.Scatter(
                x=predictions_df["timestamp"],
                y=predictions_df["predicted_value"],
                mode="lines+markers",
                name="Prediction Chronos",
                line={"color": "#dc2626", "width": 2, "dash": "dash"},
                marker={"size": 5},
            )
        )

    fig.update_layout(
        height=520,
        margin={"l": 12, "r": 12, "t": 24, "b": 12},
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        xaxis_title="Temps",
        yaxis_title="Consommation (MW)",
        template="plotly_white",
    )

    return fig


def combine_for_display(historical_df: pd.DataFrame, predictions_df: pd.DataFrame) -> pd.DataFrame:
    real = historical_df[["timestamp", "value"]].copy()
    real["type"] = "real"
    real = real.rename(columns={"value": "mw"})

    predicted = predictions_df[["timestamp", "predicted_value"]].copy()
    predicted["type"] = "prediction"
    predicted = predicted.rename(columns={"predicted_value": "mw"})

    return pd.concat([real, predicted], ignore_index=True).sort_values("timestamp")


def render_header() -> None:
    st.title("Dashboard de consommation electrique")
    st.caption("Donnees historiques RTE, predictions Chronos et stockage PostgreSQL.")


def render_sidebar(status: dict) -> tuple[datetime, datetime, str, int, int]:
    st.sidebar.header("Filtres")

    first_ts = status.get("first_historical_timestamp")
    last_ts = status.get("last_historical_timestamp")

    if pd.isna(first_ts) or pd.isna(last_ts):
        default_start = date.today() - timedelta(days=7)
        default_end = date.today()
    else:
        default_start = max(first_ts.date(), last_ts.date() - timedelta(days=7))
        default_end = last_ts.date() + timedelta(days=2)

    start_day = st.sidebar.date_input("Date de debut", value=default_start)
    end_day = st.sidebar.date_input("Date de fin", value=default_end)

    start_at = datetime.combine(start_day, time.min)
    end_at = datetime.combine(end_day, time.max)

    st.sidebar.header("Prediction")
    api_url = st.sidebar.text_input("URL FastAPI", value=DEFAULT_FASTAPI_URL)
    context_length = st.sidebar.number_input("Contexte historique (heures)", 24, 720, 168, step=24)
    prediction_length = st.sidebar.number_input("Horizon (heures)", 1, 168, 24, step=1)

    return start_at, end_at, api_url, int(context_length), int(prediction_length)


def render_metrics(status: dict, historical_df: pd.DataFrame, predictions_df: pd.DataFrame) -> None:
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Lignes historiques", f"{int(status.get('historical_rows') or 0):,}".replace(",", " "))
    col2.metric("Predictions stockees", f"{int(status.get('prediction_rows') or 0):,}".replace(",", " "))
    col3.metric("Points affiches", f"{len(historical_df) + len(predictions_df):,}".replace(",", " "))

    last_prediction_date = status.get("last_prediction_date")
    if pd.isna(last_prediction_date) or last_prediction_date is None:
        col4.metric("Derniere prediction", "Aucune")
    else:
        col4.metric("Derniere prediction", str(last_prediction_date)[:19])


def render_prediction_action(api_url: str, context_length: int, prediction_length: int) -> None:
    st.subheader("Generer une prediction")

    left, right = st.columns([1, 3])
    with left:
        run_prediction = st.button("Generer et stocker", type="primary", use_container_width=True)

    with right:
        st.info(
            "Le bouton lit les dernieres valeurs de historical_data, appelle FastAPI /predict, "
            "puis insere ou met a jour la table predictions."
        )

    if not run_prediction:
        return

    try:
        with st.spinner("Prediction Chronos en cours..."):
            context, latest_timestamp = load_latest_context(context_length)
            api_response = call_prediction_api(api_url, context, prediction_length)
            inserted = insert_predictions(api_response, latest_timestamp)

        st.success(f"{inserted} predictions inserees ou mises a jour.")
    except requests.ConnectionError:
        st.error("FastAPI est injoignable. Lance d'abord le serveur uvicorn sur le port 8000.")
    except requests.HTTPError as exc:
        st.error(f"FastAPI a retourne une erreur: {exc.response.text}")
    except Exception as exc:
        st.error(str(exc))


def main() -> None:
    render_header()

    try:
        status = load_status()
    except Exception as exc:
        st.error(f"Impossible de se connecter a PostgreSQL: {exc}")
        st.stop()

    start_at, end_at, api_url, context_length, prediction_length = render_sidebar(status)

    historical_df = load_historical_data(start_at, end_at)
    predictions_df = load_predictions(start_at, end_at)

    render_metrics(status, historical_df, predictions_df)

    fig = build_forecast_figure(historical_df, predictions_df)
    st.plotly_chart(fig, use_container_width=True)

    render_prediction_action(api_url, context_length, prediction_length)

    tab_real, tab_predictions, tab_combined = st.tabs(
        ["Historique", "Predictions", "Vue combinee"]
    )

    with tab_real:
        st.dataframe(historical_df, use_container_width=True, hide_index=True)

    with tab_predictions:
        st.dataframe(predictions_df, use_container_width=True, hide_index=True)

    with tab_combined:
        st.dataframe(
            combine_for_display(historical_df, predictions_df),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
