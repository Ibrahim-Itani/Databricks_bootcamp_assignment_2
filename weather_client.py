"""
Client for the Weather API.

No need for an API Key. NWS Weather API should return unstructured narrative text, great to create embeddings.
"""

import base64
import hashlib
import os
from datetime import datetime
from typing import Any

import requests

_BASE_URL = os.environ.get("MASSIVE_API_BASE_URL", "https://api.weather.gov")

_DEFAULT_TIMEOUT = 30

class WeatherClient:
  """Thin wrapper around the NWS Weather API + retry-friendly session.
  GET /alerts/active?area={state} → active weather alerts, each with a free-text description and instruction field (e.g., "A Flash Flood Warning means...").
  GET /gridpoints/{office}/{x},{y}/forecast → multi-day forecast with a narrative detailedForecast string per period (e.g., "Sunny, with a high near 78. Northwest wind around 6 mph.").
  GET /gridpoints/{office}/{x},{y}/forecast/hourly → hourly narrative forecasts."""
  
  def __init__(self):
    """Initialize the Weather client with a session."""
    self.session = requests.Session()
    self.session.headers.update({
      "User-Agent": "(Databricks Weather App, contact@example.com)",  # NWS requires a User-Agent
      "Accept": "application/geo+json"
    })
    self.base_url = _BASE_URL
  
  def get_active_alerts(self, state: str) -> dict[str, Any]:
    """Fetch active weather alerts for a given state.
    
    Args:
      state: Two-letter state code (e.g., 'CA', 'TX')
    
    Returns:
      Dict containing alert features with rich narrative text in
      properties.description and properties.instruction fields.
    """
    url = f"{self.base_url}/alerts/active"
    params = {"area": state.upper()}
    
    response = self.session.get(url, params=params, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()
  
  def get_forecast(self, office: str, grid_x: int, grid_y: int) -> dict[str, Any]:
    """Fetch multi-day forecast with narrative text.
    
    Args:
      office: NWS Weather Forecast Office identifier (e.g., 'LOX' for Los Angeles)
      grid_x: Grid X coordinate
      grid_y: Grid Y coordinate
    
    Returns:
      Dict with forecast periods, each containing a detailedForecast
      narrative string (e.g., "Sunny, with a high near 78...")
    """
    url = f"{self.base_url}/gridpoints/{office}/{grid_x},{grid_y}/forecast"
    
    response = self.session.get(url, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()
  
  def get_hourly_forecast(self, office: str, grid_x: int, grid_y: int) -> dict[str, Any]:
    """Fetch hourly forecast with narrative text.
    
    Args:
      office: NWS Weather Forecast Office identifier
      grid_x: Grid X coordinate
      grid_y: Grid Y coordinate
    
    Returns:
      Dict with hourly forecast periods with narrative descriptions
    """
    url = f"{self.base_url}/gridpoints/{office}/{grid_x},{grid_y}/forecast/hourly"
    
    response = self.session.get(url, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()
  
  def get_grid_point(self, latitude: float, longitude: float) -> dict[str, Any]:
    """Convert lat/lon to NWS grid coordinates.
    
    Args:
      latitude: Latitude coordinate
      longitude: Longitude coordinate
    
    Returns:
      Dict containing the gridId, gridX, and gridY needed for forecast calls
    """
    url = f"{self.base_url}/points/{latitude},{longitude}"
    
    response = self.session.get(url, timeout=_DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()


def geocode_location(location_str: str) -> tuple[float, float] | None:
  """Simple geocoding for major US cities. In production, use a real geocoding API.
  
  Args:
    location_str: Location string like "Chicago, IL" or "lat,lon" format
  
  Returns:
    Tuple of (latitude, longitude) or None if not found
  """
  # Try to parse as lat,lon first
  try:
    parts = location_str.strip().split(',')
    if len(parts) == 2:
      lat = float(parts[0].strip())
      lon = float(parts[1].strip())
      # Basic validation for lat/lon ranges
      if -90 <= lat <= 90 and -180 <= lon <= 180:
        return (lat, lon)
  except ValueError:
    pass
  
  # Simple city lookup (expand as needed)
  city_coords = {
    "chicago, il": (41.8781, -87.6298),
    "austin, tx": (30.2672, -97.7431),
    "new york, ny": (40.7128, -74.0060),
    "los angeles, ca": (34.0522, -118.2437),
    "san francisco, ca": (37.7749, -122.4194),
    "seattle, wa": (47.6062, -122.3321),
    "miami, fl": (25.7617, -80.1918),
    "denver, co": (39.7392, -104.9903),
    "boston, ma": (42.3601, -71.0589),
    "atlanta, ga": (33.7490, -84.3880),
  }
  
  return city_coords.get(location_str.lower())


def normalize_alert(alert_feature: dict, location: str) -> dict[str, Any]:
  """Normalize a weather alert feature into our database format.
  
  Args:
    alert_feature: GeoJSON feature from NWS alerts API
    location: Original location string
  
  Returns:
    Dict ready for database insertion
  """
  props = alert_feature.get("properties", {})
  
  # Create a unique ID from alert ID or hash of content
  alert_id = props.get("id") or hashlib.sha256(
    f"{location}:{props.get('event')}:{props.get('onset')}".encode()
  ).hexdigest()[:16]
  
  # Combine description and instruction for rich narrative text
  description = props.get("description", "")
  instruction = props.get("instruction", "")
  narrative = f"{description}\n\n{instruction}" if instruction else description
  
  return {
    "id": alert_id,
    "location": location,
    "source_type": "alert",
    "headline": props.get("event") or props.get("headline") or "Weather Alert",
    "narrative_text": narrative,
    "issued_at": props.get("onset") or props.get("sent"),
    "payload": alert_feature,
  }


def normalize_forecast(forecast_period: dict, location: str, office: str, grid_x: int, grid_y: int) -> dict[str, Any]:
  """Normalize a forecast period into our database format.
  
  Args:
    forecast_period: Single period from NWS forecast API
    location: Original location string
    office: NWS office identifier
    grid_x: Grid X coordinate
    grid_y: Grid Y coordinate
  
  Returns:
    Dict ready for database insertion
  """
  # Create unique ID from location and period info
  period_id = hashlib.sha256(
    f"{location}:{office}:{grid_x},{grid_y}:{forecast_period.get('number')}:{forecast_period.get('startTime')}".encode()
  ).hexdigest()[:16]
  
  return {
    "id": period_id,
    "location": location,
    "source_type": "forecast",
    "headline": forecast_period.get("name", "Forecast"),
    "narrative_text": forecast_period.get("detailedForecast", ""),
    "issued_at": forecast_period.get("startTime"),
    "payload": forecast_period,
  }


def sync_weather_data(locations: list[str], limit: int = 50) -> int:
  """Fetch weather alerts and forecasts for given locations and sync to database.
  
  Args:
    locations: List of location strings ("City, ST" or "lat,lon")
    limit: Maximum number of documents to sync per location
  
  Returns:
    Total count of documents synced
  """
  client = WeatherClient()
  all_documents = []
  
  for location in locations:
    # Geocode the location
    coords = geocode_location(location)
    if not coords:
      print(f"Warning: Could not geocode location '{location}', skipping")
      continue
    
    lat, lon = coords
    
    try:
      # Get grid point info
      grid_data = client.get_grid_point(lat, lon)
      grid_props = grid_data.get("properties", {})
      office = grid_props.get("gridId")
      grid_x = grid_props.get("gridX")
      grid_y = grid_props.get("gridY")
      
      if not all([office, grid_x, grid_y]):
        print(f"Warning: Could not get grid data for {location}, skipping")
        continue
      
      # Fetch active alerts for the state (extract from location)
      try:
        state = location.split(",")[-1].strip() if "," in location else None
        if state and len(state) == 2:
          alerts_data = client.get_active_alerts(state)
          for feature in alerts_data.get("features", [])[:limit]:
            all_documents.append(normalize_alert(feature, location))
      except Exception as e:
        print(f"Warning: Could not fetch alerts for {location}: {e}")
      
      # Fetch forecast
      try:
        forecast_data = client.get_forecast(office, grid_x, grid_y)
        for period in forecast_data.get("properties", {}).get("periods", [])[:limit]:
          all_documents.append(normalize_forecast(period, location, office, grid_x, grid_y))
      except Exception as e:
        print(f"Warning: Could not fetch forecast for {location}: {e}")
      
    except Exception as e:
      print(f"Error processing location '{location}': {e}")
      continue
  
  # Upsert into database
  if not all_documents:
    return 0
  
  # Lazy import to avoid module initialization issues
  from lakebase import get_connection
  
  with get_connection() as conn:
    with conn.cursor() as cur:
      # Use INSERT ... ON CONFLICT DO UPDATE for upsert
      upsert_sql = """
        INSERT INTO weather_documents (
          id, location, source_type, headline, narrative_text, issued_at, payload, synced_at
        ) VALUES (
          %(id)s, %(location)s, %(source_type)s, %(headline)s, %(narrative_text)s, 
          %(issued_at)s, %(payload)s, NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
          location = EXCLUDED.location,
          source_type = EXCLUDED.source_type,
          headline = EXCLUDED.headline,
          narrative_text = EXCLUDED.narrative_text,
          issued_at = EXCLUDED.issued_at,
          payload = EXCLUDED.payload,
          synced_at = NOW()
      """
      
      for doc in all_documents:
        cur.execute(upsert_sql, doc)
      
      conn.commit()
      return len(all_documents)
