from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.config import settings
from app.services.llm.gemini import GeminiProvider
from app.services.llm.provider import LLMProvider

# Import tools for direct execution
# In a larger system, we'd have a ToolRegistry
from app.api.mcp import zilean_service, torbox_service 
# Wait, we can't import `mcp` here easily due to circular deps if mcp imports vector.
# Better to pass tool execution context or have a dedicated registry.
# For now, let's re-import services directly or use a registry pattern.
# Actually, services like `zilean_service` are singletons in their modules.

from app.services.zilean import zilean_service
from app.services.torbox import torbox_service
from app.services.trakt import create_trakt_service
from app.services.tmdb import tmdb_service

class VectorService:
    def __init__(self):
        # We can default to Gemini for now, but design allows swapping
        self.provider: LLMProvider = GeminiProvider()
        self.initialized = False

    async def initialize(self, api_key: Optional[str] = None):
        # Priority: Client Key > Env Key
        final_key = api_key or settings.GEMINI_API_KEY
        
        # Re-configure if key changes or not initialized
        # Note: In a real multi-user env, we shouldn't re-configure a global singleton.
        # We should instantiate a provider per request or pass auth context to the provider.
        # For simplicity here, we re-configure (assuming single user or low concurrency for prototype).
        if final_key:
             await self.provider.configure(final_key)
             self.initialized = True

    async def chat(self, query: str, history: List[Dict[str, str]] = [], api_key: Optional[str] = None, user_context: Optional[str] = None, trakt_token: Optional[str] = None) -> str:
        """
        Process a chat query using the LLM Provider and available tools.
        """
        await self.initialize(api_key)

        # Define Available Tools (Schema)
        # This mirrors what we send in 'tools/list' but is internal for the LLM prompt
        # Tools available to the AI
        tools_schema = [
            {
                "name": "tmdb_search",
                "description": "Search TMDB to get accurate TMDB IDs for movies or TV shows. ALWAYS use this for recommendations!",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Title to search for"},
                        "type": {"type": "string", "enum": ["movie", "show"], "description": "Content type"}
                    },
                    "required": ["query", "type"]
                }
            },
            {
                "name": "search",
                "description": "Search for streams. Use only if you need to find available torrents.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "type": {"type": "string", "enum": ["movie", "show"]}
                    },
                    "required": ["query"]
                }
            }
        ]
        
        # Add Trakt tools if token is available
        if trakt_token:
            tools_schema.extend([
                {
                    "name": "trakt_stats",
                    "description": "Get the user's Trakt watching statistics (total episodes, movies, time spent, etc.)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                },
                {
                    "name": "trakt_history_search",
                    "description": "Search the user's entire watch history for a specific title. Useful for 'Did I watch X?' questions.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Title to search for"}
                        },
                        "required": ["title"]
                    }
                },
                {
                    "name": "trakt_continue_watching",
                    "description": "Get shows/movies the user is currently watching (Continue Watching list)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }
            ])

        # System Prompt
        system_prompt = """
        You are VECTOR, an advanced AI assistant embedded in the VOID streaming app.
        
        CRITICAL RULE - DEEP LINKING:
        When recommending content, you MUST provide clickable deep links.
        
        1. ALWAYS use the 'tmdb_search' tool to get accurate TMDB IDs for ANY content you recommend.
        2. Format links as: [Title](void://<type>/<tmdb_id>) where type is 'movie' or 'show'.
        3. NEVER guess or use your knowledge for TMDB IDs - only use IDs returned by tmdb_search.
        4. Limit tmdb_search calls to 3-4 titles per response to avoid overwhelming the system.
        
        Example workflow:
        - User asks: "Recommend a sci-fi show"
        - You call: tmdb_search(query="The Expanse", type="show")
        - Tool returns: {"tmdb_id": 63639, "title": "The Expanse", ...}
        - You respond: "I recommend [The Expanse](void://show/63639)..."
        
        Always provide these links for recommendations so users can immediately access content.
        """

        # Inject User Context if provided
        final_query = query
        if user_context:
            final_query = f"{query}\n\n[Active User Context]\n{user_context}"

        # 1. First Call to LLM
        # We append the new user query to history
        # We also prepend the System Prompt
        current_messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": final_query}]
        
        response = await self.provider.complete(current_messages, tools=tools_schema)
        
        # 2. Check for Tool Calls
        if response.tool_calls:
            logger.info(f"AI requested tool calls: {response.tool_calls}")
            
            # Execute Tools
            # Create a new history entry for the Model's tool request?
            # Gemini handles this via function calling history. 
            # Ideally `complete` handles the turn if we were using a persisted session object.
            # Since we are stateless HTTP, we need to manually reconstruct the conversation flow 
            # if we want to support multi-turn tool use in one request?
            # Usually: User -> Model(Call Tool) -> Sys(Result) -> Model(Final Answer)
            
            # For this MVP, we do one loop.
            tool_outputs = []
            
            for tool in response.tool_calls:
                if tool.name == "tmdb_search":
                    # Execute TMDB Search
                    args = tool.arguments
                    query = args.get("query")
                    content_type = args.get("type", "show")
                    logger.info(f"Executing tmdb_search: {query} (type={content_type})")
                    
                    try:
                        if content_type == "show":
                            result = await tmdb_service.search_show(query)
                        else:
                            result = await tmdb_service.search_movie(query)
                        
                        if result:
                            tool_outputs.append({
                                "tool": "tmdb_search",
                                "result": f"TMDB ID: {result['tmdb_id']}, Title: {result['title']}, Year: {result.get('year', 'N/A')}"
                            })
                        else:
                            tool_outputs.append({
                                "tool": "tmdb_search",
                                "result": f"No results found for '{query}'"
                            })
                    except Exception as e:
                        logger.error(f"TMDB search error: {e}")
                        tool_outputs.append({
                            "tool": "tmdb_search",
                            "result": f"Error searching TMDB: {str(e)}"
                        })
                
                elif tool.name == "search":
                    # Execute Search
                    args = tool.arguments
                    logger.info(f"Executing Search: {args}")
                    
                    q = args.get("query")
                    t = args.get("type", "movie")
                    
                    # Call Zilean (Reusing logic from mcp.py would be ideal, but for now duplicate/call service directly)
                    # Simple title search for now
                    results = await zilean_service.search_stream(title=q)
                    
                    # Simplify results for LLM consumption (don't send 1000 lines of JSON)
                    summary = [f"{r.get('raw_title')} ({r.get('size')})" for r in results[:5]]
                    tool_outputs.append({
                        "tool": "search",
                        "result": f"Found {len(results)} results. Top 5: {', '.join(summary)}"
                    })
                
                elif tool.name == "trakt_stats" and trakt_token:
                    logger.info("Executing trakt_stats")
                    trakt = create_trakt_service(trakt_token)
                    try:
                        stats = await trakt.get_watching_stats()
                        # Format stats for AI
                        movies_watched = stats.get("movies", {}).get("watched", 0)
                        episodes_watched = stats.get("episodes", {}).get("watched", 0)
                        minutes_watched = stats.get("minutes", 0)
                        hours = minutes_watched // 60
                        
                        result_text = f"User has watched {movies_watched} movies and {episodes_watched} episodes. Total time: {hours} hours."
                        tool_outputs.append({"tool": "trakt_stats", "result": result_text})
                    except Exception as e:
                        logger.error(f"Trakt stats error: {e}")
                        tool_outputs.append({"tool": "trakt_stats", "result": f"Error fetching stats: {str(e)}"})
                
                elif tool.name == "trakt_history_search" and trakt_token:
                    args = tool.arguments
                    title = args.get("title", "")
                    logger.info(f"Executing trakt_history_search for: {title}")
                    
                    trakt = create_trakt_service(trakt_token)
                    try:
                        results = await trakt.search_history(title)
                        if results:
                            result_text = f"Yes, user watched '{title}'. Found {len(results)} occurrences in history."
                        else:
                            result_text = f"No, user has not watched '{title}'."
                        tool_outputs.append({"tool": "trakt_history_search", "result": result_text})
                    except Exception as e:
                        logger.error(f"Trakt history search error: {e}")
                        tool_outputs.append({"tool": "trakt_history_search", "result": f"Error searching history: {str(e)}"})
                
                elif tool.name == "trakt_continue_watching" and trakt_token:
                    logger.info("Executing trakt_continue_watching")
                    trakt = create_trakt_service(trakt_token)
                    try:
                        items = await trakt.get_continue_watching()
                        if items:
                            summaries = []
                            for item in items[:5]:  # Top 5
                                title = item.get("show", {}).get("title") or item.get("movie", {}).get("title", "Unknown")
                                summaries.append(title)
                            result_text = f"User is currently watching: {', '.join(summaries)}"
                        else:
                            result_text = "No shows currently in progress."
                        tool_outputs.append({"tool": "trakt_continue_watching", "result": result_text})
                    except Exception as e:
                        logger.error(f"Trakt continue watching error: {e}")
                        tool_outputs.append({"tool": "trakt_continue_watching", "result": f"Error fetching continue watching: {str(e)}"})

            # 3. Feed results back to LLM
            # We construct a synthetic history:
            # [...History, UserQuery, ModelResponse(ToolCall), FunctionResponse(Result)]
            
            # Note: Gemini Provider `complete` method recreated the chat session each time.
            # To feed back results, we need to call it again with updated history.
            # Constructing "FunctionResponse" messages for Gemini is specific.
            # For this generic abstraction, let's just append a System message with the result 
            # and ask for the final answer.
            
            tool_result_text = "\n".join([f"Tool '{to['tool']}' Output: {to['result']}" for to in tool_outputs])
            
            follow_up_messages = current_messages + [
                {"role": "assistant", "content": "I need to check the database..."}, # Placeholder for tool thought
                {"role": "user", "content": f"System Tool Output:\n{tool_result_text}\n\nBased on these results, please answer the user's original question."}
            ]
            
            final_response = await self.provider.complete(follow_up_messages)
            return final_response.content

        return response.content

vector_service = VectorService()
