import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from loguru import logger
from app.utils.parser import VideoParser

from app.services.zilean import zilean_service
from app.services.torbox import torbox_service
from app.services.vector import vector_service
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
            # Return VOID-compatible manifest with explicit service names
            # VOID will display these exact labels in the Settings UI
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "name": "Omega",
                    "version": "1.0.0",
                    "description": "Multi-source provider with automatic Zilean DMM cache search",
                    "capabilities": ["source_provider", "resolver"],
                    "auth": {
                        "type": "multi_key",
                        "services": [
                            {
                                "id": "torbox",
                                "name": "TorBox",
                                "key_label": "TorBox API Key",
                                "required": False
                            },
                            {
                                "id": "realdebrid",
                                "name": "Real-Debrid",
                                "key_label": "Real-Debrid API Token",
                                "required": False
                            },
                            {
                                "id": "gemini",
                                "name": "Google Gemini",
                                "key_label": "Gemini API Key",
                                "required": False
                            }
                        ]
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
                            "description": "Resolve a stream via TorBox or Real-Debrid",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "source_id": {"type": "string"},
                                    "info_hash": {"type": "string"},
                                    "season": {"type": "integer"},
                                    "episode": {"type": "integer"},
                                    "api_keys": {
                                        "type": "object",
                                        "properties": {
                                            "torbox": {"type": "string"},
                                            "realdebrid": {"type": "string"}
                                        }
                                    },
                                    "exclude_hevc": {"type": "boolean"},
                                    "exclude_eac3": {"type": "boolean"},
                                    "exclude_dolby_vision": {"type": "boolean"}
                                }
                            }
                        },
                        {
                            "name": "vector_chat",
                            "description": "Chat with the VECTOR AI Agent",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "history": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "role": {"type": "string"},
                                                "content": {"type": "string"}
                                            }
                                        }
                                    },
                                    "api_key": {"type": "string"},
                                    "user_context": {
                                        "type": "string",
                                        "description": "Additional context (e.g. watch history) to inform the AI."
                                    }
                                },
                                "required": ["query"]
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
                # Attempt 1: Structured Search
                results = await zilean_service.search_stream(
                    title=title, 
                    year=year, 
                    imdb_id=imdb, 
                    season=season, 
                    episode=episode
                )

                # Attempt 2: Fallback to String Query (if no results and is a show)
                if not results and media_type == "show" and season and episode:
                    fallback_query = f"{title} S{season:02d}E{episode:02d}"
                    logger.info(f"Structured search returned 0 results. Trying fallback: {fallback_query}")
                    results = await zilean_service.search_stream(
                        title=fallback_query,
                        # Clear specific filters to rely on string matching
                        year=None,
                        imdb_id=None, 
                        season=None,
                        episode=None
                    )

                # Attempt 3: Desperation Search (Title Only)
                # If "Show S01E02" fails, try just "Show Name" and hoping Zilean finds a Season Pack or misnamed file.
                if not results and media_type == "show":
                    logger.info(f"Fallback search returned 0 results. Trying desperation search: {title}")
                    desperation_results = await zilean_service.search_stream(
                        title=title,
                        year=None,
                        imdb_id=None, 
                        season=None,
                        episode=None
                    )
                    
                    # Smart Filter: Remove obvious mismatches to reduce clutter
                    # Regex to find SxxEyy or 1x02 patterns
                    if desperation_results and season:
                        filtered_desperation = []
                        import re
                        
                        # Patterns: S01E02, 1x02, S01
                        # We want to keep:
                        # 1. Exact Episode Matches
                        # 2. Season Packs (Match Season, No Episode)
                        # 3. Ambiguous files (No S/E detected)
                        
                        for item in desperation_results:
                            item_title = (item.get("raw_title") or item.get("filename") or "").upper()
                            
                            # Parse Season
                            # Look for S01, Season 1, 1x
                            s_match = re.search(r'(?:S|SEASON\W?)(\d{1,2})|(\d{1,2})[xX]\d+', item_title)
                            item_season = int(s_match.group(1) or s_match.group(2)) if s_match else None
                            
                            # Parse Episode
                            # Look for E01, x01
                            e_match = re.search(r'[xE](\d{1,3})', item_title)
                            item_episode = int(e_match.group(1)) if e_match else None
                            
                            # Logic:
                            # If we detect a Season, it MUST match the requested season
                            if item_season and item_season != season:
                                continue # Wrong Season
                                
                            # If we detect an Episode, it MUST match the requested episode
                            # UNLESS we want to allow full season packs, but usually season packs don't have "E01" in the main title 
                            # (or if they do, it's usually "S01E01-E10")
                            # For safety, if we see a specific single episode number that ISN'T ours, skip it.
                            if item_episode and episode and item_episode != episode:
                                # Check for multi-episode range (e.g. E01-E10) - simplifying for now
                                # If simple mismatch, skip
                                continue 
                                
                            filtered_desperation.append(item)
                            
                        logger.info(f"Desperation search found {len(desperation_results)}, filtered to {len(filtered_desperation)}")
                        results = filtered_desperation
                    else:
                        results = desperation_results
                
                # Format for MCP
                # We return a list of "StreamSource" compatible JSONs
                # For now, just raw dump; Client agg should handle it if mapped correctly,
                # OR we map it here to standard VOID format.
                # Let's map to standard VOID structure:
                # { "id": "hash", "name": "...", "size": "...", "provider": "Omega", "info_hash": "..." }
                
                def format_size(size_bytes):
                    if not size_bytes:
                        return "Unknown"
                    try:
                        bytes_val = float(size_bytes)
                        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                            if bytes_val < 1024.0:
                                return f"{bytes_val:.2f} {unit}"
                            bytes_val /= 1024.0
                        return f"{bytes_val:.2f} PB"
                    except:
                        return "Unknown"

                def infer_quality(title):
                    lower = title.lower()
                    if "2160p" in lower or "4k" in lower:
                        return "4K"
                    if "1080p" in lower:
                        return "1080p"
                    if "720p" in lower:
                        return "720p"
                    if "480p" in lower:
                        return "480p"
                    return "Unknown"

                def safe_int(val):
                    try:
                        return int(val)
                    except:
                        return None

                mapped_results = []
                for res in results:
                    # Note: Need real Zilean response structure here.
                    # Assuming Zilean returns list of {raw_title, size, info_hash}
                    filename = res.get("filename") or res.get("raw_title") or query
                    
                    # Zilean might return 'size' as string or 'size_bytes' as int
                    raw_size = res.get("size_bytes")
                    if raw_size is None and str(res.get("size", "")).isdigit():
                         raw_size = res.get("size")
                         
                    mapped_results.append({
                        "id": res.get("info_hash"),
                        "provider": "VOID Omega MCP", # Must match Server Name for client routing
                        "title": filename,
                        "size": format_size(raw_size or res.get("size")), 
                        "size_bytes": safe_int(raw_size),
                        "quality": infer_quality(filename) + (f" [{VideoParser.get_release_group(filename)}]" if VideoParser.get_release_group(filename) else ""),
                        "info_hash": res.get("info_hash"),
                        "type": "movie", # TODO: infer
                        "cached": True # Zilean results are always cached
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
                # Get API keys from VOID client (passed via manifest)
                api_keys = args.get("api_keys", {})
                
                # Auto-detect which service to use based on available keys
                # Priority: torbox > realdebrid
                debrid_service = None
                api_key = None
                service_used = None
                
                # Check TorBox
                if api_keys.get("torbox"):
                    api_key = api_keys["torbox"]
                    debrid_service = torbox_service
                    service_used = "TorBox"
                    logger.info("Using TorBox for resolution")
                    
                # Check Real-Debrid
                elif api_keys.get("realdebrid"):
                    api_key = api_keys["realdebrid"]
                    from app.services.realdebrid import RealDebridService
                    debrid_service = RealDebridService()
                    service_used = "Real-Debrid"
                    logger.info("Using Real-Debrid for resolution")
                    
                # Fallback to env vars (local testing only)
                elif settings.TORBOX_API_KEY:
                    api_key = settings.TORBOX_API_KEY
                    debrid_service = torbox_service
                    service_used = "TorBox (env)"
                    logger.info("Using fallback TorBox key from environment")
                    
                elif settings.REALDEBRID_API_KEY:
                    api_key = settings.REALDEBRID_API_KEY
                    from app.services.realdebrid import RealDebridService
                    debrid_service = RealDebridService()
                    service_used = "Real-Debrid (env)"
                    logger.info("Using fallback Real-Debrid key from environment")
                
                if not debrid_service or not api_key:
                    return {
                        "jsonrpc": "2.0", 
                        "id": req_id, 
                        "error": {
                            "code": -32000, 
                            "message": "No API keys configured. Please add TorBox or Real-Debrid API key in VOID Settings → MCP Settings → Omega."
                        }
                    }

                info_hash = args.get("info_hash")
                if not info_hash:
                     return {
                        "jsonrpc": "2.0", "id": req_id, 
                        "error": {"code": -32602, "message": "Missing info_hash"}
                    }

                source_id = args.get("source_id") or info_hash
                magnet = args.get("magnet") or ""
                season = args.get("season")
                episode = args.get("episode")
                
                exclude_hevc = args.get("exclude_hevc", False)
                exclude_eac3 = args.get("exclude_eac3", False)
                exclude_dolby_vision = args.get("exclude_dolby_vision", False)

                stream_url = await debrid_service.resolve_stream(
                    source_id=source_id,
                    info_hash=info_hash,
                    magnet=magnet,
                    api_key=api_key,
                    season=season,
                    episode=episode,
                    exclude_hevc=exclude_hevc,
                    exclude_eac3=exclude_eac3,
                    exclude_dolby_vision=exclude_dolby_vision
                )
                
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

            elif tool_name == "vector_chat":
                query = args.get("query")
                history = args.get("history", [])
                api_key = args.get("api_key")
                user_context = args.get("user_context")
                
                response_text = await vector_service.chat(query, history, api_key, user_context)
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": response_text}
                        ]
                    }
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
