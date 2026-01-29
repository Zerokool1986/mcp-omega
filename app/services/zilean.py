import httpx
from loguru import logger
from typing import List, Optional, Any
from app.core.config import settings

class ZileanService:
    def __init__(self):
        self.base_url = settings.ZILEAN_API_URL
        self.client = httpx.AsyncClient(timeout=10.0)

    async def search_stream(self, title: str, year: int = None, imdb_id: str = None) -> List[dict]:
        """
        Search Zilean for DMM-verified cached streams.
        """
        try:
            #Zilean API endpoint: /dmm/filtered
            # Query parameter should be the search string
            params = {"Query": title}  # Capital Q based on common DMM implementations
            
            logger.info(f"Zilean Search: {self.base_url}/dmm/filtered with params {params}")
            response = await self.client.get(f"{self.base_url}/dmm/filtered", params=params) 
            response.raise_for_status()
            
            results = response.json()
            logger.info(f"Zilean returned {len(results) if isinstance(results, list) else 0} results")
            
            # Transform to generic internal format
            return results if isinstance(results, list) else []
            
        except Exception as e:
            logger.error(f"Zilean Search Failed: {e}")
            return []

zilean_service = ZileanService()
