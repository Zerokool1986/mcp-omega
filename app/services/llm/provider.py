from typing import List, Dict, Any, Protocol
from pydantic import BaseModel

class ToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]

class LLMResponse(BaseModel):
    content: str
    tool_calls: List[ToolCall] = []

class LLMProvider(Protocol):
    async def configure(self, api_key: str):
        """Initialize the provider with API credentials."""
        ...

    async def complete(
        self, 
        messages: List[Dict[str, str]], 
        tools: List[Dict[str, Any]] = []
    ) -> LLMResponse:
        """
        Send messages and available tools to the LLM.
        Returns text content and/or tool call requests.
        """
        ...
