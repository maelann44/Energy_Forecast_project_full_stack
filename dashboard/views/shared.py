from datetime import date, datetime, time, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from dashboard.database import (
    dataset_tables_exist,
    insert_predictions,
    load_actual_data,
    load_latest_context,
    load_predictions,
    load_status,
)
from dashboard.prediction_client import call_prediction_api
from dashboard.settings import ADMIN_PASSWORD, DEFAULT_FASTAPI_URL, DatasetConfig


def render_header(config: DatasetConfig) -> None:
    st.title(config.title)
    st.caption(config.caption)


def is_admin_unlocked(config: DatasetConfig) -> bool:
    if not ADMIN_PASSWORD:
        return False

    password = st.sidebar.text_input("Mot de passe admin", type="password", key=f"{config.key}_admin_password")
    return password == ADMIN_PASSWORD


def get_available_years(status: dict) -> list[int]:
    first_ts = status.get("first_historical_timestamp")
    last_ts = status.get("last_historical_timestamp")

    if pd.isna(first_ts) or pd.isna(last_ts) or first_ts is None or last_ts is None:
        return [date.today().year]

    return list(range(first_ts.year, last_ts.year + 1))


def render_sidebar(config: DatasetConfig, status: dict) -> tuple[datetime, datetime, str, int, int, bool]:
    st.sidebar.header("Filtres")

    first_ts = status.get("first_historical_timestamp")
    last_ts = status.get("last_historical_timestamp")
    filter_mode = st.sidebar.radio(
        "Selection",
        ["Periode", "Annee"],
        horizontal=True,
        key=f"{config.key}_filter_mode",
    )

    if filter_mode == "Annee":
        years = get_available_years(status)
        selected_year = st.sidebar.selectbox("Annee", years, index=len(years) - 1, key=f"{config.key}_year")
        start_at = datetime.combine(date(selected_year, 1, 1), time.min)
        end_at = datetime.combine(date(selected_year, 12, 31), time.max)
    else:
        if pd.isna(first_ts) or pd.isna(last_ts) or first_ts is None or last_ts is None:
            default_start = date.today() - timedelta(days=7)
            default_end = date.today()
        else:
            default_start = max(first_ts.date(), last_ts.date() - timedelta(days=7))
            default_end = last_ts.date() + timedelta(days=2)

        start_day = st.sidebar.date_input("Date de debut", value=default_start, key=f"{config.key}_start_day")
        end_day = st.sidebar.date_input("Date de fin", value=default_end, key=f"{config.key}_end_day")

        start_at = datetime.combine(start_day, time.min)
        end_at = datetime.combine(end_day, time.max)

    st.sidebar.header("Prediction")
    api_url = st.sidebar.text_input("URL FastAPI", value=DEFAULT_FASTAPI_URL, key=f"{config.key}_api_url")
    context_length = st.sidebar.number_input(
        "Contexte historique (heures)",
        24,
        720,
        168,
        step=24,
        key=f"{config.key}_context_length",
    )
    prediction_length = st.sidebar.number_input(
        "Horizon (heures)",
        1,
        168,
        24,
        step=1,
        key=f"{config.key}_prediction_length",
    )
    admin_unlocked = is_admin_unlocked(config)

    return start_at, end_at, api_url, int(context_length), int(prediction_length), admin_unlocked


def render_metrics(config: DatasetConfig, status: dict, actual_df: pd.DataFrame, predictions_df: pd.DataFrame) -> None:
    col1, col2, col3, col4 = st.columns(4)

    col1.metric(f"Lignes {config.value_label.lower()}", f"{int(status.get('historical_rows') or 0):,}".replace(",", " "))
    col2.metric("Predictions stockees", f"{int(status.get('prediction_rows') or 0):,}".replace(",", " "))
    col3.metric("Points affiches", f"{len(actual_df) + len(predictions_df):,}".replace(",", " "))

    last_prediction_date = status.get("last_prediction_date")
    if pd.isna(last_prediction_date) or last_prediction_date is None:
        col4.metric("Derniere prediction", "Aucune")
    else:
        col4.metric("Derniere prediction", str(last_prediction_date)[:19])


def build_forecast_figure(config: DatasetConfig, actual_df: pd.DataFrame, predictions_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()

    if not actual_df.empty:
        fig.add_trace(
            go.Scatter(
                x=actual_df["timestamp"],
                y=actual_df["value"],
                mode="lines",
                name=config.actual_trace_name,
                line={"color": "#2563eb", "width": 2},
            )
        )

    if not predictions_df.empty:
        fig.add_trace(
            go.Scatter(
                x=predictions_df["timestamp"],
                y=predictions_df["predicted_value"],
                mode="lines+markers",
                name=config.prediction_trace_name,
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
        yaxis_title=config.yaxis_title,
        template="plotly_white",
    )

    return fig


def combine_for_display(config: DatasetConfig, actual_df: pd.DataFrame, predictions_df: pd.DataFrame) -> pd.DataFrame:
    real = actual_df[["timestamp", "value"]].copy()
    real["type"] = "real"
    real = real.rename(columns={"value": config.combined_value_column})

    predicted = predictions_df[["timestamp", "predicted_value"]].copy()
    predicted["type"] = "prediction"
    predicted = predicted.rename(columns={"predicted_value": config.combined_value_column})

    return pd.concat([real, predicted], ignore_index=True).sort_values("timestamp")


def render_prediction_action(
    config: DatasetConfig,
    api_url: str,
    context_length: int,
    prediction_length: int,
    admin_unlocked: bool,
) -> None:
    st.subheader("Generer une prediction")

    if not ADMIN_PASSWORD:
        st.warning(
            "Action desactivee: definir DASHBOARD_ADMIN_PASSWORD dans .env pour autoriser "
            "la generation manuelle de predictions."
        )
        return

    if not admin_unlocked:
        st.info("Mode lecture seule. Entrez le mot de passe admin dans la barre laterale pour generer une prediction.")
        return

    left, right = st.columns([1, 3])
    with left:
        run_prediction = st.button("Generer et stocker", type="primary", use_container_width=True, key=f"{config.key}_run_prediction")

    with right:
        st.info(
            f"Le bouton lit les dernieres valeurs de {config.actual_table}, appelle FastAPI /predict, "
            f"puis insere ou met a jour la table {config.prediction_table}."
        )

    if not run_prediction:
        return

    try:
        with st.spinner("Prediction Chronos en cours..."):
            context, latest_timestamp = load_latest_context(config, context_length)
            api_response = call_prediction_api(api_url, context, prediction_length)
            inserted = insert_predictions(config, api_response, latest_timestamp)

        st.success(f"{inserted} predictions inserees ou mises a jour.")
    except requests.ConnectionError:
        st.error("FastAPI est injoignable. Lance d'abord le serveur uvicorn sur le port 8000.")
    except requests.HTTPError as exc:
        st.error(f"FastAPI a retourne une erreur: {exc.response.text}")
    except Exception as exc:
        st.error(str(exc))


def render_missing_tables(config: DatasetConfig) -> None:
    st.warning(
        f"Les tables `{config.actual_table}` et `{config.prediction_table}` ne sont pas encore disponibles "
        "dans PostgreSQL pour cette page."
    )
    st.code(
        f"""
-- Tables attendues pour la page {config.menu_label}
{config.actual_table}
{config.prediction_table}
""".strip(),
        language="sql",
    )
    st.info(
        "Pour une base deja existante, applique la migration "
        "`database/migrations/03_imbalance_tables.sql`. Pour une nouvelle base, "
        "`database/init/01_schema.sql` creera les tables automatiquement."
    )


def render_dataset_page(config: DatasetConfig) -> None:
    render_header(config)

    try:
        if not dataset_tables_exist(config):
            render_missing_tables(config)
            return

        status = load_status(config)
    except Exception as exc:
        st.error(f"Impossible de se connecter a PostgreSQL: {exc}")
        st.stop()

    start_at, end_at, api_url, context_length, prediction_length, admin_unlocked = render_sidebar(config, status)

    actual_df = load_actual_data(config, start_at, end_at)
    predictions_df = load_predictions(config, start_at, end_at)

    render_metrics(config, status, actual_df, predictions_df)

    fig = build_forecast_figure(config, actual_df, predictions_df)
    st.plotly_chart(fig, use_container_width=True)

    render_prediction_action(config, api_url, context_length, prediction_length, admin_unlocked)

    tab_real, tab_predictions, tab_combined = st.tabs(
        ["Historique", "Predictions", "Vue combinee"]
    )

    with tab_real:
        st.dataframe(actual_df, use_container_width=True, hide_index=True)

    with tab_predictions:
        st.dataframe(predictions_df, use_container_width=True, hide_index=True)

    with tab_combined:
        st.dataframe(
            combine_for_display(config, actual_df, predictions_df),
            use_container_width=True,
            hide_index=True,
        )
