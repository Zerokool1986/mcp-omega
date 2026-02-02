import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content
from typing import List, Dict, Any
from loguru import logger
from .provider import LLMProvider, LLMResponse, ToolCall

class GeminiProvider(LLMProvider):
    def __init__(self):
        self.model = None

    async def configure(self, api_key: str):
        if not api_key:
            logger.warning("Gemini Provider initialized without API Key")
            return
        genai.configure(api_key=api_key)
        # Use Flash 1.5 for speed/cost efficiency
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def complete(
        self, 
        messages: List[Dict[str, str]], 
        tools: List[Dict[str, Any]] = []
    ) -> LLMResponse:
        if not self.model:
            return LLMResponse(content="Error: Gemini AI not configured. Please set GEMINI_API_KEY in server environment.")

        # Convert conversation history to Gemini format
        gemini_history = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        # Separate the last user message as the active prompt
        if gemini_history and gemini_history[-1]["role"] == "user":
            last_message = gemini_history.pop()
            prompt = last_message["parts"][0]
        else:
            prompt = "Hello" # Fallback

        # Convert Tools to Gemini Function Declarations
        gemini_tools = None
        if tools:
            formatted_tools = []
            for t in tools:
                formatted_tools.append(
                     content.FunctionDeclaration(
                         name=t["name"],
                         description=t["description"],
                         parameters=self._map_schema(t["inputSchema"])
                     )
                 )
            
            gemini_tools = content.Tool(function_declarations=formatted_tools)

        try:
            # Create a chat session with history
            chat = self.model.start_chat(history=gemini_history)
            
            # Send message
            if gemini_tools:
                # Re-instantiate model with tools if needed
                chat = genai.GenerativeModel(
                    'gemini-1.5-flash', 
                    tools=[gemini_tools]
                ).start_chat(history=gemini_history)

            response = await chat.send_message_async(prompt)
            
            # Parse Response
            text_content = ""
            tool_calls = []

            for part in response.parts:
                if part.text:
                    text_content += part.text
                if part.function_call:
                    fc = part.function_call
                    # Convert args to dict protocol
                    args = dict(fc.args.items()) 
                    tool_calls.append(ToolCall(name=fc.name, arguments=args))

            return LLMResponse(content=text_content, tool_calls=tool_calls)

        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return LLMResponse(content=f"Error connecting to AI: {str(e)}")

    def _map_schema(self, schema: Dict[str, Any]) -> content.Schema:
        """Converts a standard JSON Schema dict to a Gemini content.Schema object."""
        type_str = schema.get("type", "string").lower()
        
        type_map = {
            "string": content.Type.STRING,
            "number": content.Type.NUMBER, 
            "integer": content.Type.INTEGER,
            "boolean": content.Type.BOOLEAN,
            "array": content.Type.ARRAY,
            "object": content.Type.OBJECT
        }
        
        gemini_type = type_map.get(type_str, content.Type.STRING)
        
        properties = {}
        if "properties" in schema:
            for key, prop_schema in schema["properties"].items():
                properties[key] = self._map_schema(prop_schema)
                
        return content.Schema(
            type=gemini_type,
            description=schema.get("description"),
            properties=properties or None,
            required=schema.get("required"),
            enum=schema.get("enum")
        )
