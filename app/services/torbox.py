import httpx
import asyncio
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
            logger.info(f"TorBox Create Response: {data}")

            if not data.get("success"):
                 logger.error(f"TorBox Add Error: {data}")
                 return None
            
            # Check if 'data' block itself contains file info (sometimes it does)
            torrent_info = data.get("data", {})
            torrent_id = torrent_info.get("torrent_id") or torrent_info.get("id")
            files_from_create = torrent_info.get("files") # Optimistic check

            if not torrent_id:
                logger.error("Could not determine Torrent ID from TorBox response")
                return None
            
            target_torrent = None

            # If create response already gave us the files, use them!
            if files_from_create:
                logger.info("TorBox returned files in create response, skipping list lookups")
                target_torrent = torrent_info
            else:
                # 2. Get Torrent Info (fallback) with Retries
                # Sometimes a "cached" torrent takes a moment to hydrate the files list (stuck in metaDL).
                
                for attempt in range(3):
                    logger.info(f"Fetching TorBox list for ID: {torrent_id} (Attempt {attempt+1}/3)")
                    
                    info_resp = await self.client.get(f"{self.base_url}/api/torrents/mylist?bypass_cache=true", headers=headers)
                    info_data = info_resp.json()
                    
                    # Log less to keep it clean, but enough to debug
                    logger.info(f"TorBox MyList Success={info_data.get('success')}")
                    
                    if info_data.get("success"):
                        for t in info_data.get("data", []):
                            if str(t.get("id")) == str(torrent_id):
                                target_torrent = t
                                break
                    
                    if target_torrent:
                        state = target_torrent.get("download_state")
                        files = target_torrent.get("files", [])
                        logger.info(f"Torrent State: {state}, Files: {len(files)}")
                        
                        if files:
                            # We have files, we are good!
                            break
                        else:
                            # Found torrent, but no files yet (metaDL?). Wait and retry.
                            logger.warning("Torrent found but has no files (hydrating?). Waiting...")
                    
                    if attempt < 2:
                        await asyncio.sleep(1.5)
                        # Reset for next loop to force re-fetch
                        target_torrent = None 
            
            if not target_torrent:
                logger.error(f"Torrent {torrent_id} added but not found in list.")
                return None
                
            # Find best file (largest video)
            files = target_torrent.get("files", [])
            best_file_id = None
            
            if not files:
                 logger.error("No suitable files found in torrent (even after retries)")
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
