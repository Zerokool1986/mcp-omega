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
        # Gemini expects "user" and "model" roles
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
        gemini_tools = []
        if tools:
            # We need to map generic JSON Schema to Gemini's expected format
            # Fortunately, Gemini supports JSON Schema-like dicts
            # We wrap them in a Tool object
            # Note: For simplicity in this iteration, we might pass tools directly if supported,
            # or we need to construct FunctionDeclaration objects.
            
            # Using the simpler "tools" argument in generate_content which accepts list of functions
            # But we have JSON definitions.
            # We'll need to define python functions or construct `genai.types.FunctionDeclaration`
            pass 
            # TODO: Implement full schema mapping. 
            # For this MVP step, we will rely on text-based tool prompting if schema mapping fails, 
            # OR we assume 'tools' contains valid FunctionDeclarations.
            
            # Revisit: For now, let's keep it simple. 
            # We will use system prompt instructions for tool usage in this first pass 
            # to avoid complex schema translation code, OR strictly map if we have time.
            # Let's try basic schema mapping.

            formatted_tools = []
            for t in tools:
                 # Check if we can construct function declaration
                 # simplistic mapping
                 formatted_tools.append(
                     content.FunctionDeclaration(
                         name=t["name"],
                         description=t["description"],
                         parameters=t["inputSchema"]
                     )
                 )
            
            gemini_tools = content.Tool(function_declarations=formatted_tools)

        try:
            # Create a chat session with history
            chat = self.model.start_chat(history=gemini_history)
            
            # Send message
            # If tools are present, we pass them.
            # Note: start_chat doesn't accept tools easily in 1.0, 
            # we might need to recreate model with tools=...
            
            if gemini_tools:
                # Re-instantiate model with tools if needed, or use generate_content
                # ChatSession binding is preferred.
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
                    args = dict(fc.args.items()) # generic proto map to dict
                    tool_calls.append(ToolCall(name=fc.name, arguments=args))

            return LLMResponse(content=text_content, tool_calls=tool_calls)

        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            return LLMResponse(content=f"Error connecting to AI: {str(e)}")
