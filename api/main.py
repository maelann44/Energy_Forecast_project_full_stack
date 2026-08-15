import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

try:
    from chronos import BaseChronosPipeline as ChronosPipelineClass
except ImportError:
    from chronos import ChronosPipeline as ChronosPipelineClass


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = os.getenv("CHRONOS_MODEL_NAME", "amazon/chronos-t5-small")
DEVICE_MAP = os.getenv("CHRONOS_DEVICE_MAP", "cpu")
DEFAULT_QUANTILES = [0.1, 0.5, 0.9]

model_state: dict[str, Any] = {"pipeline": None}


class PredictRequest(BaseModel):
    context: list[float] = Field(
        ...,
        min_length=4,
        description="Historique de consommation, par exemple les 168 dernieres heures.",
    )
    prediction_length: int = Field(
        24,
        ge=1,
        le=168,
        description="Nombre de pas de temps a predire.",
    )
    quantiles: list[float] = Field(
        default=DEFAULT_QUANTILES,
        description="Quantiles probabilistes demandes.",
    )

    @field_validator("context")
    @classmethod
    def context_values_must_be_valid(cls, values: list[float]) -> list[float]:
        if any(value < 0 for value in values):
            raise ValueError("Les valeurs de consommation doivent etre positives.")
        return values

    @field_validator("quantiles")
    @classmethod
    def quantiles_must_be_valid(cls, values: list[float]) -> list[float]:
        if not values:
            raise ValueError("Il faut fournir au moins un quantile.")
        if any(value <= 0 or value >= 1 for value in values):
            raise ValueError("Chaque quantile doit etre strictement entre 0 et 1.")
        return sorted(values)


class PredictionPoint(BaseModel):
    step: int
    predicted_value: float
    quantiles: dict[str, float]


class PredictResponse(BaseModel):
    model_name: str
    prediction_length: int
    context_length: int
    predictions: list[PredictionPoint]


class HealthResponse(BaseModel):
    status: str
    model_name: str
    model_loaded: bool
    device_map: str


def get_torch_dtype() -> torch.dtype:
    if DEVICE_MAP == "cpu":
        return torch.float32
    return torch.bfloat16


def load_model():
    return ChronosPipelineClass.from_pretrained(
        MODEL_NAME,
        device_map=DEVICE_MAP,
        torch_dtype=get_torch_dtype(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    model_state["pipeline"] = load_model()
    yield


app = FastAPI(
    title="Electricity Forecast API",
    description="API FastAPI pour servir le modele Chronos de forecast de consommation electrique.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_name=MODEL_NAME,
        model_loaded=model_state["pipeline"] is not None,
        device_map=DEVICE_MAP,
    )


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest) -> PredictResponse:
    pipeline = model_state["pipeline"]
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Modele Chronos non charge.")

    context = torch.tensor(payload.context, dtype=torch.float32)

    try:
        with torch.no_grad():
            forecast = pipeline.predict(context, payload.prediction_length)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur pendant la prediction: {exc}") from exc

    samples = forecast[0].detach().cpu().numpy()
    quantile_array = np.quantile(samples, payload.quantiles, axis=0)
    mean_values = samples.mean(axis=0)

    predictions: list[PredictionPoint] = []
    for step in range(payload.prediction_length):
        quantiles = {
            f"q{int(quantile * 100)}": float(quantile_array[index, step])
            for index, quantile in enumerate(payload.quantiles)
        }
        predicted_value = quantiles.get("q50", float(mean_values[step]))
        predictions.append(
            PredictionPoint(
                step=step + 1,
                predicted_value=float(predicted_value),
                quantiles=quantiles,
            )
        )

    return PredictResponse(
        model_name=MODEL_NAME,
        prediction_length=payload.prediction_length,
        context_length=len(payload.context),
        predictions=predictions,
    )
