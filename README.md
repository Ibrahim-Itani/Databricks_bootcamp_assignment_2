# Databricks Bootcamp Assignment 2: Weather Data + Embeddings

Context engineering pipeline for weather alerts and forecasts using the National Weather Service (NWS) API and vector embeddings.

## README_WEATHER

### 1. Data Source Choice

**Chosen:** National Weather Service (NWS) API

**Why:**
* **Rich narrative text**: Weather alerts and forecasts contain detailed, natural language descriptions perfect for semantic search
* **No API key required**: Freely accessible public data
* **Real-time updates**: Active alerts and forecasts change frequently, demonstrating live data ingestion
* **Domain diversity**: Mix of alert types (heat advisories, fog warnings, severe weather) and forecast periods provides varied content
* **Public domain**: No licensing concerns for educational/production use

### 2. Schema & Design Decisions

**Documents Table (`weather_documents`):**
* `id` (TEXT): Unique identifier from NWS or hash-based for forecasts
* `location` (TEXT): Human-readable location for filtering/display
* `source_type` (TEXT): 'alert' or 'forecast' for categorization
* `headline` (TEXT): Short title for quick scanning
* `narrative_text` (TEXT): Full unstructured text for embeddings
* `issued_at` (TIMESTAMPTZ): Temporal filtering and freshness
* `payload` (JSONB): Complete API response for future extensibility

**Embeddings Table (`weather_documents_embeddings`):**
* `embedding` (VECTOR(384)): Uses `all-MiniLM-L6-v2` model
  - **Model choice**: Balance of speed, size, and quality for production
  - **384 dimensions**: Smaller than alternatives (768/1024), faster search
  - **No chunking**: Weather documents are already bite-sized (200-500 words)
  - **Embedding text**: Concatenates `location + '. ' + headline` for context-aware search

**Why no chunking?**
* Weather alerts/forecasts are naturally short (1-2 paragraphs)
* Chunking would fragment already-concise content
* Each document represents a single semantic unit (one alert, one forecast period)

### 3. End-to-End Pipeline

**Step 1: Database Setup**
```bash
psql $LAKEBASE_URL
\i sql/01_setup_weather_documents_table.sql
\i sql/02_setup_embeddings_table.sql
```

**Step 2: Sync Weather Data**
```python
from weather_client import sync_weather_data
sync_weather_data(["Chicago, IL", "New York, NY"], limit=50)
```

**Step 3: Generate Embeddings** (run notebook cells 1-12 in order)
```python
# Or via notebook: notebooks/ingest_weather_data.ipynb
# Loads weather_documents → computes embeddings → stores in weather_documents_embeddings
```

**Step 4: Search**
```bash
# Start Flask app
python app.py

# Open browser: http://localhost:5000
# Or use API:
curl -X POST http://localhost:5000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "heat advisory", "top_k": 5}'
```

### 4. Known Limitations & Future Improvements

**Current Limitations:**
* **Limited geocoding**: Only 10 pre-configured cities; requires manual lat/lon for others
* **US-only coverage**: NWS API only covers US territories
* **No real-time updates**: Data is manually synced, not continuously ingested
* **Basic error handling**: NWS API failures may silently skip locations
* **Single embedding model**: No A/B testing or model versioning

**Future Improvements:**
* **Real geocoding API**: Integrate Google Maps/OpenStreetMap for any location
* **Scheduled sync**: Databricks Jobs to refresh data hourly/daily
* **Incremental updates**: Only fetch new alerts/forecasts since last sync
* **Multi-modal embeddings**: Include weather severity, location metadata
* **Reranking**: Add cross-encoder reranking for improved top-K precision
* **Monitoring**: Track data freshness, embedding drift, search quality metrics
* **Global coverage**: Add additional weather APIs (OpenWeatherMap, Weather Underground)
* **Hybrid search**: Combine vector similarity with keyword matching and filters (date, location, severity)

## Overview

This project demonstrates:

1. **Weather Data Ingestion**: Fetching rich narrative text from NWS API (alerts, forecasts)
2. **Vector Embeddings**: Creating semantic embeddings for similarity search
3. **Lakebase Postgres**: Storing documents and pgvector embeddings
4. **REST API**: Flask endpoint for triggering data sync

## Architecture

```
NWS API → weather_client.py → Lakebase (weather_documents)
                            ↓
                  ingest_weather_embeddings.py
                            ↓
            Lakebase (weather_documents_embeddings)
```

## Setup

### 1. Prerequisites

```bash
pip install -r requirements.txt
```

### 2. Database Setup

Run the SQL scripts in order:

```bash
# Connect to your Lakebase Postgres instance
psql $LAKEBASE_URL

# Create tables
\i sql/01_setup_weather_documents_table.sql
\i sql/02_setup_embeddings_table.sql
```

### 3. Configure Secrets

Store your Lakebase connection URL in Databricks secrets:

```bash
databricks secrets create-scope database
databricks secrets put --scope database --key lakebase-url
# Paste base64-encoded PostgreSQL URL:
# postgresql://role:password@host:5432/db?sslmode=require
```

## Usage

### Option 1: Direct Python Call

```python
from weather_client import sync_weather_data

locations = [
    "Chicago, IL",
    "Austin, TX",
    "40.7128,-74.0060",  # Can also use lat,lon
]

count = sync_weather_data(locations, limit=50)
print(f"Synced {count} weather documents")
```

### Option 2: Flask API

```bash
# Start the Flask server
python app.py

# In another terminal, trigger sync
curl -X POST http://localhost:5000/weather/sync \
  -H "Content-Type: application/json" \
  -d '{
    "locations": ["Seattle, WA", "Miami, FL"],
    "limit": 50
  }'
```

Response:
```json
{
  "success": true,
  "documents_synced": 42,
  "message": "Successfully synced 42 weather documents"
}
```

### Option 3: Test Script

```bash
python test_weather_sync.py
```

### Option 4: Databricks Notebook

Run the [ingest_weather_embeddings.py](#notebook-2422032476942614) notebook to:

1. Fetch weather data from NWS
2. Compute embeddings using sentence-transformers
3. Store both documents and embeddings in Lakebase

## API Reference

### WeatherClient

```python
from weather_client import WeatherClient

client = WeatherClient()

# Get active alerts for a state
alerts = client.get_active_alerts("CA")

# Get forecast (requires grid coordinates)
forecast = client.get_forecast("LOX", 154, 47)

# Get hourly forecast
hourly = client.get_hourly_forecast("LOX", 154, 47)

# Convert lat/lon to grid coordinates
grid_info = client.get_grid_point(34.0522, -118.2437)
```

### Flask Endpoints

#### `POST /weather/sync`

Sync weather data for specified locations.

**Request:**
```json
{
  "locations": ["Chicago, IL", "Austin, TX"],
  "limit": 50
}
```

**Response:**
```json
{
  "success": true,
  "documents_synced": 42,
  "message": "Successfully synced 42 weather documents"
}
```

#### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "weather-sync"
}
```

## Database Schema

### weather_documents

```sql
CREATE TABLE weather_documents (
    id TEXT PRIMARY KEY,
    location TEXT NOT NULL,
    source_type TEXT CHECK (source_type IN ('alert', 'forecast')),
    headline TEXT NOT NULL,
    narrative_text TEXT NOT NULL,  -- Rich unstructured text for embeddings
    issued_at TIMESTAMPTZ,
    payload JSONB NOT NULL,
    synced_at TIMESTAMPTZ DEFAULT now()
);
```

### weather_documents_embeddings

```sql
CREATE TABLE weather_documents_embeddings (
    id TEXT PRIMARY KEY,
    location TEXT NOT NULL,
    headline TEXT NOT NULL,
    published_utc TIMESTAMPTZ,
    embedding VECTOR(384) NOT NULL,  -- pgvector for semantic search
    model_name TEXT NOT NULL,
    embedded_at TIMESTAMPTZ DEFAULT now()
);
```

## Supported Locations

### Format 1: City, State

```python
locations = [
    "Chicago, IL",
    "Austin, TX",
    "New York, NY",
    "Los Angeles, CA",
    "San Francisco, CA",
    "Seattle, WA",
    "Miami, FL",
    "Denver, CO",
    "Boston, MA",
    "Atlanta, GA",
]
```

### Format 2: Latitude, Longitude

```python
locations = [
    "41.8781,-87.6298",  # Chicago
    "30.2672,-97.7431",  # Austin
]
```

## NWS API Details

The National Weather Service API provides:

* **No API key required** ✓
* **Rich narrative text** perfect for embeddings:
  * Alert descriptions: "A Flash Flood Warning means..."
  * Detailed forecasts: "Sunny, with a high near 78. Northwest wind around 6 mph."
* **Public domain data**

### Rate Limits

* Requires User-Agent header (configured in `weather_client.py`)
* Be respectful with request frequency
* Serial fetching (not distributed) to stay within limits

## Files

* **weather_client.py**: NWS API client + sync logic
* **app.py**: Flask REST API
* **lakebase.py**: Postgres connection helper
* **test_weather_sync.py**: Test script
* **notebooks/ingest_weather_embeddings.py**: Full ETL + embeddings pipeline
* **sql/**: Database setup scripts

## Example Queries

### Find similar weather alerts

```python
import psycopg2
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Create query embedding
query = "tornado warning high winds"
query_embedding = model.encode([query])[0]

# Search using cosine similarity
with psycopg2.connect(lakebase_url) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT location, headline, narrative_text,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM weather_documents_embeddings
            ORDER BY embedding <=> %s::vector
            LIMIT 5
        """, (query_embedding.tolist(), query_embedding.tolist()))
        
        for row in cur.fetchall():
            print(f"{row[3]:.3f} - {row[1]} ({row[0]})")
```

## License

MIT