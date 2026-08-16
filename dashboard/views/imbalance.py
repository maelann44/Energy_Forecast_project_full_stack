from dashboard.settings import DATASETS
from dashboard.views.shared import render_dataset_page


def render() -> None:
    render_dataset_page(DATASETS["imbalance"])
