# VOID Omega MCP Server

The flagship, generic Media Content Provider for VOID.

## Features
- **Tier 1 (Speed)**: Zilean (Instant DMM Cache)
- **Tier 2 (Backup)**: TorBox (Debrid & Cache Check)

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

## Environment Variables
Create a `.env` file to override defaults:
```env
TORBOX_API_KEY=your_key_here
```
(Alternatively, pass the API key from the VOID App settings when calling the tool).
