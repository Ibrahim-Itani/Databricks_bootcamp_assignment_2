# Quick Start Guide

## 1. Set up Database Tables

```bash
# Connect to Lakebase
psql $LAKEBASE_URL

# Run setup scripts
\i sql/01_setup_weather_documents_table.sql
\i sql/02_setup_embeddings_table.sql
```

## 2. Test Weather Client

### Python Direct Call

```python
from weather_client import sync_weather_data

# Sync weather for multiple locations
count = sync_weather_data([
    "Chicago, IL",
    "Austin, TX",
    "34.0522,-118.2437"  # Los Angeles (lat,lon)
], limit=10)

print(f"Synced {count} documents")
```

### Flask API

```bash
# Terminal 1: Start Flask server
python app.py

# Terminal 2: Test endpoint
curl -X POST http://localhost:5000/weather/sync \
  -H "Content-Type: application/json" \
  -d '{
    "locations": ["Seattle, WA", "Miami, FL"],
    "limit": 20
  }'
```

## 3. Generate Embeddings

Run the Databricks notebook:

```python
# In notebooks/ingest_weather_embeddings.py
# This notebook will:
# 1. Read weather_documents table
# 2. Compute embeddings using sentence-transformers
# 3. Store vectors in weather_documents_embeddings
```

## 4. Query Similar Documents

### Option A: Web UI (Recommended)

1. Start the Flask server:
```bash
python app.py
```

2. Open your browser to `http://localhost:5000`

3. Enter a search query like:
   - "heat advisory in Chicago"
   - "fog warning"
   - "severe weather alerts"

4. Adjust the number of results (1-20) and click **Search**

The UI will display the most relevant weather documents with similarity scores.

### Option B: REST API

```bash
curl -X POST http://localhost:5000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "heat advisory in Chicago",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "success": true,
  "query": "heat advisory in Chicago",
  "results": [
    {
      "location": "Chicago, IL",
      "headline": "Heat Advisory",
      "chunk_text": "Heat index values between 100 and 105...",
      "similarity": 0.85,
      "published_utc": "2026-08-09T17:00:00Z"
    }
  ],
  "count": 5
}
```

### Option C: Python Code

```python
import psycopg2
from sentence_transformers import SentenceTransformer
from lakebase import get_connection

model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# Create query embedding
query = "severe thunderstorm warning"
query_vec = model.encode([query])[0].tolist()

# Find similar weather documents
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                location,
                headline,
                LEFT(narrative_text, 200) as snippet,
                1 - (embedding <=> %s::vector) as similarity
            FROM weather_documents_embeddings
            ORDER BY embedding <=> %s::vector
            LIMIT 5
        """, (query_vec, query_vec))
        
        print("\nTop 5 Similar Weather Documents:")
        print("=" * 80)
        for row in cur.fetchall():
            print(f"\n{row['similarity']:.3f} - {row['headline']} ({row['location']})")
            print(f"  {row['snippet']}...")
```

## Project Structure

```
Databricks_bootcamp_assignment_2/
├── weather_client.py           # NWS API client + sync logic
├── app.py                       # Flask REST API with vector search
├── lakebase.py                  # Postgres connection helper
├── requirements.txt             # Python dependencies
├── sql/
│   ├── 01_setup_weather_documents_table.sql
│   └── 02_setup_embeddings_table.sql
├── templates/
│   └── index.html               # Vector search web UI
└── notebooks/
    └── ingest_weather_data.ipynb  # Full ETL pipeline
```

## API Endpoints

### Health Check
```bash
GET /health
```

### Sync Weather Data
```bash
POST /weather/sync
Content-Type: application/json

{
  "locations": ["Chicago, IL", "Austin, TX"],
  "limit": 50
}
```

### Vector Search
```bash
POST /search
Content-Type: application/json

{
  "query": "heat advisory in Chicago",
  "top_k": 5
}
```

### Web UI
```bash
GET /
```
Serves the interactive vector search interface.

## Supported Locations

Pre-configured cities:
* Chicago, IL
* Austin, TX
* New York, NY
* Los Angeles, CA
* San Francisco, CA
* Seattle, WA
* Miami, FL
* Denver, CO
* Boston, MA
* Atlanta, GA

Or use lat,lon format: `"40.7128,-74.0060"`

## Common Issues

### "Could not geocode location"

The location isn't in the pre-configured city list. Either:
1. Add it to `city_coords` dict in `weather_client.py`
2. Use lat,lon format instead

### "Could not get grid data"

The NWS API doesn't have coverage for that location (likely outside US). NWS only covers US territories.

### Connection refused on Flask endpoint

Make sure Flask is running: `python app.py`

## Next Steps

1. **Expand city coverage**: Add more cities to `geocode_location()`
2. **Add real geocoding**: Integrate Google Maps or OpenStreetMap API
3. **Schedule regular syncs**: Use Databricks Jobs to run notebook on schedule
4. **Build RAG app**: Use embeddings for semantic search in a chatbot
5. **Add more NWS endpoints**: Radar data, storm reports, etc.