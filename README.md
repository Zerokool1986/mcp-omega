# VOID Omega MCP Server

The flagship, generic Media Content Provider for VOID.

## Features

### Content Discovery & Streaming
- **Tier 1 (Speed)**: Zilean (Instant DMM Cache)
- **Tier 2 (Backup)**: TorBox/Real-Debrid (Debrid & Cache Check)

### AI Assistant (Vector)
- **Conversational AI**: Gemini-powered chat interface
- **Personalized Recommendations**: Trakt integration for watch history
- **Deep Linking**: Automatic TMDB ID lookups for instant content access
- **Context-Aware**: Understands user preferences and viewing patterns

### Metadata Enrichment
- **TMDB Integration**: Accurate metadata lookups for movies and TV shows
- **Trakt Integration**: Social features, watch history, and stats

## Available Tools

### `search`
Search for movies and TV shows across torrent sources.

**Parameters:**
- `query` (string): Title to search for
- `type` (string): `movie` or `show`
- `season` (integer, optional): Season number for TV shows
- `episode` (integer, optional): Episode number for TV shows

### `resolve`
Convert a torrent hash into a streamable URL using debrid services.

**Parameters:**
- `info_hash` (string): Torrent info hash
- `api_keys` (object): Debrid service API keys (`torbox`, `realdebrid`)

### `vector_chat`
Chat with the Vector AI assistant for personalized recommendations.

**Parameters:**
- `query` (string): User's question or request
- `history` (array): Chat history for context
- `api_key` (string): Gemini API key
- `trakt_token` (string, optional): Trakt OAuth access token
- `tmdb_api_key` (string, optional): TMDB API key for metadata lookups
- `user_context` (string, optional): Additional context

**Vector AI Capabilities:**
- Personalized content recommendations based on Trakt history
- Generates deep links: `[Title](void://show/12345)` for instant playback
- Uses `tmdb_search` tool internally for accurate TMDB IDs
- Accesses Trakt stats, history, and continue watching lists

### `tmdb_search` (Internal)
Used by Vector AI to look up accurate TMDB IDs.

**Parameters:**
- `query` (string): Title to search
- `type` (string): `movie` or `show`

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run Server**:
   ```bash
   python main.py
   # OR using uvicorn directly
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Configure in VOID**:
   - Go to Settings > MCP Add-ons > (+) Add
   - URL: `http://10.0.2.2:8000/mcp/sse` (Emulator)
   - URL: `http://<YOUR_PC_IP>:8000/mcp/sse` (Physical Device)

## API Keys

### Required (Client-Provided)
- **Gemini API Key**: Required for Vector AI chat
- **TMDB API Key**: Required for Vector AI deep linking

### Optional (Client-Provided)
- **Trakt OAuth Token**: Enables personalized recommendations
- **TorBox/Real-Debrid API Key**: Required for stream resolution

### Environment Variables (Fallback)
Create a `.env` file to override defaults for local testing:
```env
GEMINI_API_KEY=your_gemini_key
TORBOX_API_KEY=your_torbox_key
REALDEBRID_API_KEY=your_realdebrid_key
```

**Note:** In production, API keys should be passed from the VOID app per-request for security.

## Architecture

### Services
- **ZileanService** (`zilean.py`): DMM cache search
- **TorBoxService** (`torbox.py`): Debrid resolution
- **VectorService** (`vector.py`): AI chat orchestration
- **TraktService** (`trakt.py`): User watch history and stats
- **TMDBService** (`tmdb.py`): Metadata lookups for accurate TMDB IDs

### Vector AI System Prompt
Vector uses a strict system prompt to ensure accurate deep linking:

1. **ALWAYS** uses `tmdb_search` tool for any content recommendations
2. Formats links as `[Title](void://<type>/<tmdb_id>)`
3. **NEVER** guesses TMDB IDs to avoid hallucinations
4. Limits searches to 3-4 per response to prevent overload

Example workflow:
- User: "Recommend a sci-fi show"
- Vector calls: `tmdb_search(query="The Expanse", type="show")`
- TMDB returns: `{"tmdb_id": 63639, "title": "The Expanse", ...}`
- Vector responds: "I recommend [The Expanse](void://show/63639)..."
