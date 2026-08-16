from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard.settings import DATASETS
from dashboard.views import consumption, imbalance


PAGE_RENDERERS = {
    "consumption": consumption.render,
    "imbalance": imbalance.render,
}


st.set_page_config(
    page_title="Energy Forecast Dashboard",
    layout="wide",
)


def render_navigation() -> str:
    labels_by_key = {key: config.menu_label for key, config in DATASETS.items()}
    selected_label = st.sidebar.radio("Page", list(labels_by_key.values()), key="dataset_page")

    for key, label in labels_by_key.items():
        if label == selected_label:
            return key

    return "consumption"


def main() -> None:
    page_key = render_navigation()
    PAGE_RENDERERS[page_key]()


if __name__ == "__main__":
    main()
