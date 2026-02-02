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

    async def chat(self, query: str, history: List[Dict[str, str]] = [], api_key: Optional[str] = None) -> str:
        """
        Process a chat query using the LLM Provider and available tools.
        """
        await self.initialize(api_key)

        # Define Available Tools (Schema)
        # This mirrors what we send in 'tools/list' but is internal for the LLM prompt
        tools_schema = [
            {
                "name": "search",
                "description": "Search for movies or displays. Input query can be a title like 'Dune' or specific like 'Severance S01E01'.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Title of the content"},
                        "type": {"type": "string", "enum": ["movie", "show"], "description": "Media type if known"},
                        "season": {"type": "integer"},
                        "episode": {"type": "integer"}
                    },
                    "required": ["query"]
                }
            },
           # We can add resolve later, for now focus on search
        ]

        # 1. First Call to LLM
        # We append the new user query to history
        current_messages = history + [{"role": "user", "content": query}]
        
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
                if tool.name == "search":
                    # Execute Search
                    args = tool.arguments
                    logger.info(f"Executing Search: {args}")
                    
                    q = args.get("query")
                    t = args.get("type", "movie")
                    pass
                    
                    # Call Zilean (Reusing logic from mcp.py would be ideal, but for now duplicate/call service directly)
                    # Simple title search for now
                    results = await zilean_service.search_stream(title=q)
                    
                    # Simplify results for LLM consumption (don't send 1000 lines of JSON)
                    summary = [f"{r.get('raw_title')} ({r.get('size')})" for r in results[:5]]
                    tool_outputs.append({
                        "tool": "search",
                        "result": f"Found {len(results)} results. Top 5: {', '.join(summary)}"
                    })

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
