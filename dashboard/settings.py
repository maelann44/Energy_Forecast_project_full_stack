from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_FASTAPI_URL = os.getenv("PREDICTION_API_URL", "http://localhost:8000/predict")
ADMIN_PASSWORD = os.getenv("DASHBOARD_ADMIN_PASSWORD")


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    menu_label: str
    title: str
    caption: str
    actual_table: str
    prediction_table: str
    value_label: str
    yaxis_title: str
    actual_trace_name: str
    prediction_trace_name: str
    combined_value_column: str
    source_name: str


DATASETS = {
    "consumption": DatasetConfig(
        key="consumption",
        menu_label="Consommation",
        title="Dashboard de consommation electrique",
        caption="Donnees historiques RTE, predictions Chronos et stockage PostgreSQL.",
        actual_table="historical_data",
        prediction_table="predictions",
        value_label="Consommation",
        yaxis_title="Consommation (MW)",
        actual_trace_name="Consommation reelle",
        prediction_trace_name="Prediction Chronos",
        combined_value_column="mw",
        source_name="RTE",
    ),
    "imbalance": DatasetConfig(
        key="imbalance",
        menu_label="Imbalance",
        title="Dashboard imbalance",
        caption="Donnees d'imbalance RTE, predictions Chronos et stockage PostgreSQL.",
        actual_table="imbalance_data",
        prediction_table="imbalance_predictions",
        value_label="Imbalance",
        yaxis_title="Imbalance (MW)",
        actual_trace_name="Imbalance reelle",
        prediction_trace_name="Prediction imbalance Chronos",
        combined_value_column="imbalance_mw",
        source_name="RTE_IMBALANCE",
    ),
}


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante: {name}")
    return value
