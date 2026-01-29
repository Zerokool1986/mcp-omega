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
            # Zilean API endpoint: /dmm/search (try this first, then /dmm/filtered)
            # Try both lowercase 'query' and IMDb ID
            params = {}
            if title:
                params["query"] = title  # Lowercase q
            if imdb_id:
                params["imdbId"] = imdb_id  # camelCase based on API schema
            
            logger.info(f"Zilean Search: {self.base_url}/dmm/search with params {params}")
            response = await self.client.get(f"{self.base_url}/dmm/search", params=params) 
            response.raise_for_status()
            
            results = response.json()
            logger.info(f"Zilean returned {len(results) if isinstance(results, list) else 0} results")
            
            # Transform to generic internal format
            return results if isinstance(results, list) else []
            
        except Exception as e:
            logger.error(f"Zilean Search Failed: {e}")
            return []

zilean_service = ZileanService()
