import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from loguru import logger

from app.services.zilean import zilean_service
from app.services.torbox import torbox_service
from app.core.config import settings

router = APIRouter()

# --- Models ---

class JsonRpcRequest(BaseModel):
    jsonrpc: str
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None

# --- SSE Endpoint ---

@router.get("/sse")
async def sse_endpoint(request: Request):
    """
    MCP Handshake via Server-Sent Events.
    """
    async def event_generator():
        # Construct the full public URL
        # Use the Host header to get the correct domain (critical for Render)
        host = request.headers.get("host", str(request.base_url).replace("http://", "").replace("https://", "").rstrip("/"))
        
        # Determine protocol (Render uses https)
        proto = "https" if "render.com" in host or request.headers.get("x-forwarded-proto") == "https" else "http"
        
        endpoint_url = f"{proto}://{host}/mcp/messages"

        logger.info(f"Client connected. Sending endpoint: {endpoint_url}")
        
        yield {
            "event": "endpoint",
            "data": endpoint_url
        }
        
        logger.info(f"Endpoint event sent successfully: {endpoint_url}")
        
        # Keep alive
        import asyncio
        while True:
            await asyncio.sleep(20)
            yield {"comment": "ping"}

    return EventSourceResponse(event_generator())

# --- JSON-RPC Endpoint ---

@router.post("/messages")
async def handle_json_rpc(request: JsonRpcRequest):
    """
    MCP Method Handler.
    """
    try:
        method = request.method
        params = request.params or {}
        req_id = request.id
        
        logger.info(f"Method: {method} | Params: {params}")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "0.1.0",
                    "capabilities": {
                         # We offer tools
                        "tools": {"listChanged": True} 
                    },
                    "serverInfo": {
                        "name": settings.PROJECT_NAME,
                        "version": settings.VERSION
                    }
                }
            }


        if method == "notifications/initialized":
             # Notifications don't get responses in JSON-RPC spec
             return Response(status_code=204)  # No Content


        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search Zilean (DMM Cache) for streams",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "imdb_id": {"type": "string"},
                                    "tmdb_id": {"type": "integer"}
                                }
                            }
                        },
                        {
                            "name": "resolve",
                            "description": "Resolve a stream via TorBox",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "source_id": {"type": "string"}, # info_hash
                                    "info_hash": {"type": "string"},
                                    "api_keys": { # Enforce passing API keys in request
                                        "type": "object",
                                        "properties": {
                                            "torbox": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            
            if tool_name == "search":
                # Client sends: title, type, imdb_id, tmdb_id, year, season, episode
                title = args.get("title")
                imdb = args.get("imdb_id")
                year = args.get("year")
                media_type = args.get("type")  # 'movie' or 'show'
                season = args.get("season")
                episode = args.get("episode")
                
                # Build search query
                query = title
                if media_type == "show" and season and episode:
                    query = f"{title} S{season:02d}E{episode:02d}"
                
                # Zilean Generic Search
                # Pass raw title; Zilean Filtered endpoint handles Season/Episode/Year filtering
                results = await zilean_service.search_stream(
                    title=title, 
                    year=year, 
                    imdb_id=imdb, 
                    season=season, 
                    episode=episode
                )
                
                # Format for MCP
                # We return a list of "StreamSource" compatible JSONs
                # For now, just raw dump; Client agg should handle it if mapped correctly,
                # OR we map it here to standard VOID format.
                # Let's map to standard VOID structure:
                # { "id": "hash", "name": "...", "size": "...", "provider": "Omega", "info_hash": "..." }
                
                mapped_results = []
                for res in results:
                    # Note: Need real Zilean response structure here.
                    # Assuming Zilean returns list of {raw_title, size, info_hash}
                    mapped_results.append({
                        "id": res.get("info_hash"),
                        "provider": "Omega/Indo (Zilean)",
                        "title": res.get("filename") or res.get("raw_title") or query,
                        "size": res.get("size_bytes", "Unknown"), # Need fmt
                        "quality": "1080p", # TODO: Parse from title
                        "info_hash": res.get("info_hash"),
                        "type": "movie" # TODO: infer
                    })
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(mapped_results)}
                        ]
                    }
                }

            elif tool_name == "resolve":
                # User should pass API keys via client "settings" or explicit args
                # In VOID MCP, sensitive keys are passed in 'api_keys' map if configured.
                api_keys = args.get("api_keys", {})
                torbox_key = api_keys.get("torbox") or settings.TORBOX_API_KEY
                
                if not torbox_key:
                    return {
                        "jsonrpc": "2.0", "id": req_id, 
                        "error": {"code": -32000, "message": "Missing TorBox API Key"}
                    }
                
                info_hash = args.get("info_hash")
                if not info_hash:
                     return {
                        "jsonrpc": "2.0", "id": req_id, 
                        "error": {"code": -32602, "message": "Missing info_hash"}
                    }

                stream_url = await torbox_service.resolve_stream(torbox_key, info_hash)
                
                if stream_url:
                     return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [
                                {"type": "text", "text": json.dumps({"success": True, "stream": {"url": stream_url}})}
                            ]
                        }
                    }
                else:
                     return {
                        "jsonrpc": "2.0", "id": req_id, 
                        "error": {"code": -32001, "message": "Failed to resolve stream"}
                    }

        return JSONResponse(
            status_code=404, 
            content={"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": req_id}
        )

    except Exception as e:
        logger.exception("MCP Error")
        return JSONResponse(
            status_code=500, 
            content={"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": request.id}
        )
