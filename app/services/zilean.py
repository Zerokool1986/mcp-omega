import httpx
from loguru import logger
from typing import List, Optional, Any
from app.core.config import settings
from async_lru import alru_cache

class ZileanService:
    def __init__(self):
        self.base_url = settings.ZILEAN_API_URL
        self.client = httpx.AsyncClient(timeout=10.0)


    async def search_stream(self, title: str, year: int = None, imdb_id: str = None, season: int = None, episode: int = None, **kwargs) -> List[dict]:
        """
        Public wrapper that calls the cached internal method.
        """
        # Convert args to hashable types if needed, but int/str are fine.
        return await self._fetch_cached(title, year, imdb_id, season, episode)

    @alru_cache(maxsize=256)
    async def _fetch_cached(self, title: str, year: int, imdb_id: str, season: int, episode: int) -> List[dict]:
        """
        Cached Zilean Search.
        """
        try:
            params = {}
            if title: params["Query"] = title
            if imdb_id: params["ImdbId"] = imdb_id
            if year: params["Year"] = year
            if season: params["Season"] = season
            if episode: params["Episode"] = episode
            
            logger.info(f"Zilean Search (Network): {self.base_url}/dmm/filtered with params {params}")
            response = await self.client.get(f"{self.base_url}/dmm/filtered", params=params) 
            response.raise_for_status()
            
            results = response.json()
            logger.info(f"Zilean returned {len(results) if isinstance(results, list) else 0} results")
            
            return results if isinstance(results, list) else []
            
        except Exception as e:
            logger.error(f"Zilean Search Failed: {e}")
            return []

zilean_service = ZileanService()
