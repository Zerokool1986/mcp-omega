import httpx
from typing import List, Dict, Any, Optional
from loguru import logger

class TraktService:
    """
    Server-side Trakt API client using user's OAuth token.
    IMPORTANT: This CLIENT_ID must match the Android app's CLIENT_ID because
    the access token was issued to that client. Using a different CLIENT_ID
    will result in 403 Forbidden errors.
    """
    
    BASE_URL = "https://api.trakt.tv"
    CLIENT_ID = "006574af3390f43c53f5db3a430ba8e08e91632c3ed23f29f7e842ec48644dfd"  # Android app's CLIENT_ID
    
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
        Get user's watched content (completed items).
        This uses /watched endpoints instead of /history for better permission compatibility.
        Returns a combined list of watched shows and movies.
        """
        results = []
        
        async with httpx.AsyncClient() as client:
            # Get watched movies
            if item_type in [None, "movies", "movie"]:
                try:
                    response = await client.get(
                        f"{self.BASE_URL}/users/me/watched/movies",
                        headers=self.headers,
                        timeout=10.0
                    )
                    response.raise_for_status()
                    movies = response.json()
                    for movie in movies[:limit]:
                        results.append({
                            "type": "movie",
                            "movie": movie.get("movie", {}),
                            "plays": movie.get("plays", 1),
                            "last_watched_at": movie.get("last_watched_at")
                        })
                except Exception as e:
                    logger.error(f"Error fetching watched movies: {e}")
            
            # Get watched shows (returns show-level data, not episodes)
            if item_type in [None, "shows", "show"]:
                try:
                    response = await client.get(
                        f"{self.BASE_URL}/users/me/watched/shows",
                        headers=self.headers,
                        timeout=10.0
                    )
                    response.raise_for_status()
                    shows = response.json()
                    for show in shows[:limit]:
                        results.append({
                            "type": "show",
                            "show": show.get("show", {}),
                            "plays": show.get("plays", 1),
                            "last_watched_at": show.get("last_watched_at")
                        })
                except Exception as e:
                    logger.error(f"Error fetching watched shows: {e}")
        
        return results[:limit]
    
    async def search_history(self, title: str) -> List[Dict[str, Any]]:
        """
        Search the user's watched content for a specific title.
        Uses /watched endpoints instead of /history for compatibility.
        """
        history = await self.get_history(limit=1000)  # Get large sample
        results = []
        
        title_lower = title.lower()
        for item in history:
            if item.get("type") == "movie":
                movie_title = item.get("movie", {}).get("title", "").lower()
                if title_lower in movie_title:
                    results.append(item)
            elif item.get("type") == "show":
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
