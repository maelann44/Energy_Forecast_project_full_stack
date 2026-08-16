import requests


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
