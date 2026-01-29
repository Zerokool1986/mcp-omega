from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "VOID Omega MCP"
    VERSION: str = "1.0.0"
    
    # Tier 1: Zilean
    ZILEAN_API_URL: str = "https://zileanfortheweebs.midnightignite.me"  # Midnight's public Zilean instance
    
    # Tier 2: Debrid Services (API Keys injected by Client or Env)
    TORBOX_API_KEY: Optional[str] = None
    REALDEBRID_API_KEY: Optional[str] = None
    
    class Config:
        env_file = ".env"

settings = Settings()
