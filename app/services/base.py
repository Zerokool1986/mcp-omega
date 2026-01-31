from abc import ABC, abstractmethod
from typing import Optional, Dict

class DebridClient(ABC):
    """
    Abstract Base Class for Debrid Providers (TorBox, RealDebrid, etc.)
    """
    
    @abstractmethod
    async def resolve_stream(
        self, 
        source_id: str, 
        info_hash: str, 
        magnet: str, 
        api_key: str, 
        season: Optional[int] = None, 
        episode: Optional[int] = None
    ) -> Optional[str]:
        """
        Resolves a magnet/hash to a direct download link.
        Must handle:
        1. Adding magnet to service
        2. Selecting correct file (Smart SxxExx matching)
        3. Unrestricting/Resolving the link
        """
        pass
