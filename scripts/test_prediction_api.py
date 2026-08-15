import argparse
import json

import pandas as pd
import requests


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Teste localement l'API FastAPI de prediction.")
    parser.add_argument("--csv-path", default="consumption_data_avg_hourly.csv")
    parser.add_argument("--api-url", default="http://localhost:8000/predict")
    parser.add_argument("--context-length", type=int, default=168)
    parser.add_argument("--prediction-length", type=int, default=24)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    df = pd.read_csv(args.csv_path)
    context = df["avg_value_hourly"].tail(args.context_length).astype(float).tolist()

    payload = {
        "context": context,
        "prediction_length": args.prediction_length,
        "quantiles": [0.1, 0.5, 0.9],
    }

    response = requests.post(args.api_url, json=payload, timeout=120)
    response.raise_for_status()

    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
