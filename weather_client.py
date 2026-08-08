"""
Client for the Weather API.

No need for an API Key. NWS Weather API should return unstructured narrative text, great to create embeddings.
"""

import base64
import os
from typing import Any

import requests
from databricks.sdk import WorkspaceClient

_w = WorkspaceClient()

_BASE_URL = os.environ.get("MASSIVE_API_BASE_URL", "https://api.weather.com")

_DEFAULT_TIMEOUT = 30

class WeatherClient:
  """Thin wrapper around the Massive API + retry-friendly session.
  GET /alerts/active?area={state} → active weather alerts, each with a free-text description and instruction field (e.g., "A Flash Flood Warning means...").
  GET /gridpoints/{office}/{x},{y}/forecast → multi-day forecast with a narrative detailedForecast string per period (e.g., "Sunny, with a high near 78. Northwest wind around 6 mph.").
  GET /gridpoints/{office}/{x},{y}/forecast/hourly → hourly narrative forecasts."""
