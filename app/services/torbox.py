import httpx
from loguru import logger
from typing import Optional, Dict
from app.core.config import settings

class TorBoxService:
    """
    Client for TorBox.app API.
    Used to resolve info_hashes from Zilean into playable links.
    """
    def __init__(self):
        self.base_url = "https://api.torbox.app/v1"
        self.client = httpx.AsyncClient(timeout=20.0)

    async def _get_headers(self, api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    async def resolve_stream(self, api_key: str, info_hash: str, file_id: Optional[str] = None) -> Optional[str]:
        """
        Takes an info_hash, adds it to TorBox, and retrieves the download link.
        """
        if not api_key:
            logger.error("No TorBox API Key provided")
            return None

        headers = await self._get_headers(api_key)
        
        try:
            # 1. Add Torrent (Instant Check)
            # TorBox 'torrent/create' handles magnets/hashes.
            # If cached, it's instant.
            add_payload = {
                "magnet": f"magnet:?xt=urn:btih:{info_hash}",
                "seed": "1", 
                "allow_zip": "false"
            }
            
            # Use data= for form-encoded (multipart/form-data not strictly needed unless file upload, but form-urlencoded is safer)
            resp = await self.client.post(f"{self.base_url}/api/torrents/createtorrent", data=add_payload, headers=headers)
            
            if resp.status_code != 200:
                logger.error(f"TorBox Add Failed: {resp.text}")
                return None
                
            data = resp.json()
            if not data.get("success"):
                 logger.error(f"TorBox Add Error: {data}")
                 return None
            
            torrent_id = data.get("data", {}).get("torrent_id")
            if not torrent_id:
                 # Sometimes it returns existing torrent info
                 torrent_id = data.get("data", {}).get("id")

            if not torrent_id:
                logger.error("Could not determine Torrent ID from TorBox response")
                return None

            # 2. Get Torrent Info (to find the file ID if not provided)
            # We need to find the largest video file if no fileIndex/ID is given.
            info_resp = await self.client.get(f"{self.base_url}/api/torrents/mylist", headers=headers)
            info_data = info_resp.json()
            
            # Find our torrent
            target_torrent = None
            if info_data.get("success"):
                for t in info_data.get("data", []):
                    if str(t.get("id")) == str(torrent_id):
                        target_torrent = t
                        break
            
            if not target_torrent:
                logger.error("Torrent added but not found in list")
                return None
                
            # Find best file (largest video)
            files = target_torrent.get("files", [])
            best_file_id = None
            
            if not files:
                # Some APIs return files in a separate endpoint or format
                pass
            else:
                # Sort by size desc
                video_files = [f for f in files if f.get("name", "").lower().endswith((".mp4", ".mkv", ".avi"))]
                if video_files:
                    video_files.sort(key=lambda x: x.get("size", 0), reverse=True)
                    best_file_id = video_files[0].get("id")
                else:
                     # Fallback to largest file period
                     files.sort(key=lambda x: x.get("size", 0), reverse=True)
                     if files:
                         best_file_id = files[0].get("id")

            if not best_file_id:
                logger.error("No suitable files found in torrent")
                return None

            # 3. Request Download Link
            link_payload = {
                "torrent_id": torrent_id,
                "file_id": best_file_id,
                "zip_link": False 
            }
            
            link_resp = await self.client.get(
                f"{self.base_url}/api/torrents/requestdl", 
                params=link_payload, 
                headers=headers
            )
            
            link_data = link_resp.json()
            if link_data.get("success"):
                return link_data.get("data")
            else:
                logger.error(f"Link Request Failed: {link_data}")
                return None

        except Exception as e:
            logger.exception(f"TorBox Resolve Exception: {e}")
            return None

torbox_service = TorBoxService()
