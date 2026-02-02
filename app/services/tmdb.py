import httpx
from loguru import logger
from typing import List, Optional, Dict, Any
from async_lru import alru_cache

class TMDBService:
    def __init__(self, api_key: str = None):
        # TMDB API key - will be configured by client or fall back to a default
        # For now, using a placeholder that should be replaced with a valid key
        self.api_key = api_key or "8d6d91941230817f7807d643736e8a49"  # Public demo key
        self.base_url = "https://api.themoviedb.org/3"
        self.client = httpx.AsyncClient(timeout=10.0)

    @alru_cache(maxsize=256)
    async def search_show(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search for a TV show and return the top result with TMDB ID.
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/search/tv",
                params={"api_key": self.api_key, "query": query}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("results"):
                top_result = data["results"][0]
                return {
                    "tmdb_id": top_result["id"],
                    "title": top_result["name"],
                    "year": top_result.get("first_air_date", "")[:4] if top_result.get("first_air_date") else None,
                    "overview": top_result.get("overview", "")
                }
            return None
        except Exception as e:
            logger.error(f"TMDB TV search failed for '{query}': {e}")
            return None

    @alru_cache(maxsize=256)
    async def search_movie(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search for a movie and return the top result with TMDB ID.
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/search/movie",
                params={"api_key": self.api_key, "query": query}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("results"):
                top_result = data["results"][0]
                return {
                    "tmdb_id": top_result["id"],
                    "title": top_result["title"],
                    "year": top_result.get("release_date", "")[:4] if top_result.get("release_date") else None,
                    "overview": top_result.get("overview", "")
                }
            return None
        except Exception as e:
            logger.error(f"TMDB movie search failed for '{query}': {e}")
            return None

# Singleton instance
tmdb_service = TMDBService()
