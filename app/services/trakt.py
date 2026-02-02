import httpx
from typing import List, Dict, Any, Optional
from loguru import logger

class TraktService:
    """
    Server-side Trakt API client using user's OAuth token.
    """
    
    BASE_URL = "https://api.trakt.tv"
    CLIENT_ID = "d82b02e4d13047a3e939301cd77f8d0799fa19fb0de1129db7ba93be58cf8be3"
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self.CLIENT_ID,
            "Authorization": f"Bearer {access_token}"
        }
    
    async def get_watching_stats(self) -> Dict[str, Any]:
        """
        Get user's watching statistics.
        Returns aggregated data on total episodes, movies, time spent, etc.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/users/me/stats",
                headers=self.headers,
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_history(self, limit: int = 100, item_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get user's watch history.
        item_type: 'movies', 'shows', 'seasons', 'episodes' (or None for all)
        """
        url = f"{self.BASE_URL}/users/me/history"
        if item_type:
            url += f"/{item_type}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=self.headers,
                params={"limit": limit},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    async def search_history(self, title: str) -> List[Dict[str, Any]]:
        """
        Search the user's entire history for a specific title.
        Useful for questions like "Did I watch Inception?"
        """
        history = await self.get_history(limit=1000)  # Get large sample
        results = []
        
        title_lower = title.lower()
        for item in history:
            if item.get("type") == "movie":
                movie_title = item.get("movie", {}).get("title", "").lower()
                if title_lower in movie_title:
                    results.append(item)
            elif item.get("type") == "episode":
                show_title = item.get("show", {}).get("title", "").lower()
                if title_lower in show_title:
                    results.append(item)
        
        return results
    
    async def get_continue_watching(self) -> List[Dict[str, Any]]:
        """
        Get shows/movies the user is currently watching.
        This combines 'watching' and 'progress'.
        """
        # Trakt doesn't have a native "Continue Watching" endpoint
        # We simulate it by getting recently watched shows that are incomplete
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/users/me/watching",
                headers=self.headers,
                timeout=10.0
            )
            
            if response.status_code == 204:  # No Content (not currently watching)
                # Fallback: Get progress for shows
                progress_response = await client.get(
                    f"{self.BASE_URL}/users/me/watched/shows",
                    headers=self.headers,
                    timeout=10.0
                )
                progress_response.raise_for_status()
                return progress_response.json()
            
            response.raise_for_status()
            return [response.json()]  # Single item if actively watching
    
    async def get_calendar(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get upcoming episodes for shows the user watches.
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/calendars/my/shows",
                headers=self.headers,
                params={"days": days},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_favorite_genres(self) -> List[str]:
        """
        Determine user's favorite genres based on watch history.
        """
        stats = await self.get_watching_stats()
        
        # Extract genre data from stats if available
        # Trakt stats don't directly provide genres, so we'd need to aggregate from history
        # For now, return empty list as placeholder
        # In production, you'd analyze history items' genres
        return []


# Singleton instance (will be recreated per request with user's token)
def create_trakt_service(access_token: str) -> TraktService:
    """Factory function to create a TraktService with a user's token."""
    return TraktService(access_token)
