"""
Flask API for Weather Data Sync and Vector Search.

Provides endpoints to sync weather alerts and forecasts from NWS API into
the Lakebase weather_documents table, and semantic search over embeddings.
"""

import os
import numpy as np
from flask import Flask, jsonify, request, render_template
from sentence_transformers import SentenceTransformer

from weather_client import sync_weather_data
from lakebase import get_connection

app = Flask(__name__)

# Load embedding model on startup
EMBEDDING_MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDINGS_TABLE_NAME = os.environ.get("EMBEDDINGS_TABLE_NAME", "weather_documents_embeddings")

print(f"Loading embedding model {EMBEDDING_MODEL_NAME}...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME, cache_folder="/tmp/.cache/huggingface")


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "weather-sync"}), 200


@app.route("/weather/sync", methods=["POST"])
def sync_weather():
    """Sync weather data for given locations.
    
    Expected JSON body:
    {
      "locations": ["Chicago, IL", "Austin, TX"],
      "limit": 50  // optional, defaults to 50
    }
    
    Returns:
    {
      "success": true,
      "documents_synced": 42,
      "message": "Successfully synced 42 weather documents"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "Missing JSON body"
            }), 400
        
        locations = data.get("locations", [])
        if not locations:
            return jsonify({
                "success": False,
                "error": "Missing 'locations' field or empty list"
            }), 400
        
        if not isinstance(locations, list):
            return jsonify({
                "success": False,
                "error": "'locations' must be a list of strings"
            }), 400
        
        limit = data.get("limit", 50)
        if not isinstance(limit, int) or limit < 1:
            return jsonify({
                "success": False,
                "error": "'limit' must be a positive integer"
            }), 400
        
        # Sync weather data
        count = sync_weather_data(locations, limit)
        
        return jsonify({
            "success": True,
            "documents_synced": count,
            "message": f"Successfully synced {count} weather documents"
        }), 200
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/", methods=["GET"])
def index():
    """Serve the vector search UI."""
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def vector_search():
    """Semantic search over weather document embeddings.
    
    Expected JSON body:
    {
      "query": "heat advisory in Chicago",
      "top_k": 5  // optional, defaults to 5, clamped to 1-20
    }
    
    Returns:
    {
      "success": true,
      "query": "heat advisory in Chicago",
      "results": [
        {
          "location": "Chicago, IL",
          "headline": "Heat Advisory",
          "chunk_text": "...",
          "similarity": 0.85
        },
        ...
      ]
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "Missing JSON body"
            }), 400
        
        query = data.get("query", "").strip()
        if not query:
            return jsonify({
                "success": False,
                "error": "Missing or empty 'query' field"
            }), 400
        
        # Clamp top_k to 1-20
        top_k = data.get("top_k", 5)
        if not isinstance(top_k, int):
            top_k = 5
        top_k = max(1, min(20, top_k))
        
        # Encode the query
        query_embedding = embedding_model.encode([query])[0].tolist()
        
        # Format embedding as PostgreSQL array literal
        query_vector = '{' + ','.join(str(float(x)) for x in query_embedding) + '}'
        
        # Connect to database and search
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Check if table exists and has data
                cur.execute(f"""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_name = %s
                """, (EMBEDDINGS_TABLE_NAME,))
                
                if cur.fetchone()[0] == 0:
                    return jsonify({
                        "success": False,
                        "error": f"Embeddings table '{EMBEDDINGS_TABLE_NAME}' does not exist. Please run the data sync and embedding pipeline first."
                    }), 404
                
                # Check if there's any data
                cur.execute(f"SELECT COUNT(*) FROM {EMBEDDINGS_TABLE_NAME}")
                count = cur.fetchone()[0]
                
                if count == 0:
                    return jsonify({
                        "success": True,
                        "query": query,
                        "results": [],
                        "message": "No embeddings found. Please sync weather data and compute embeddings first."
                    }), 200
                
                # Perform vector similarity search using cosine distance
                # Note: We use 1 - (embedding <=> query_vector) to convert distance to similarity
                search_sql = f"""
                    SELECT 
                        id,
                        location,
                        headline,
                        published_utc,
                        1 - (embedding::vector <=> %s::vector) AS similarity
                    FROM {EMBEDDINGS_TABLE_NAME}
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding::vector <=> %s::vector
                    LIMIT %s
                """
                
                cur.execute(search_sql, (query_vector, query_vector, top_k))
                rows = cur.fetchall()
                
                # Format results
                results = []
                for row in rows:
                    # Fetch the full narrative_text from weather_documents table
                    cur.execute(
                        "SELECT narrative_text FROM weather_documents WHERE id = %s",
                        (row['id'],)
                    )
                    narrative_row = cur.fetchone()
                    chunk_text = narrative_row['narrative_text'] if narrative_row else ""
                    
                    results.append({
                        "location": row['location'],
                        "headline": row['headline'],
                        "chunk_text": chunk_text,
                        "similarity": float(row['similarity']),
                        "published_utc": str(row['published_utc']) if row['published_utc'] else None
                    })
                
                return jsonify({
                    "success": True,
                    "query": query,
                    "results": results,
                    "count": len(results)
                }), 200
    
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    # For local development
    app.run(host="0.0.0.0", port=5000, debug=True)