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
            # Zilean API endpoint: /dmm/filtered (GET)
            # Parameters must be capitalized per OpenAPI spec: Query, ImdbId, Season, Episode, Year
            params = {}
            if title:
                params["Query"] = title
            if imdb_id:
                params["ImdbId"] = imdb_id
            if year:
                params["Year"] = year
            # Add other fields if available in kwargs, assuming they are passed correctly
            if "season" in kwargs:
                 params["Season"] = kwargs["season"]
            if "episode" in kwargs:
                 params["Episode"] = kwargs["episode"]
            
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
