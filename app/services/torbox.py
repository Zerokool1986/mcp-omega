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

    async def resolve_stream(self, source_id: str, info_hash: str, magnet: str, api_key: str, season: Optional[int] = None, episode: Optional[int] = None) -> Optional[str]:
        """
        Resolves a stream from TorBox by adding the magnet and selecting the correct file.
        """
        if not api_key:
            logger.error("No TorBox API Key provided")
            return None

        headers = await self._get_headers(api_key)
        
        try:
            # 1. Add Torrent (Instant Check)
            # TorBox 'torrent/create' handles magnets/hashes.
            # If cached, it's instant.
            
            logger.info(f"Adding torrent to TorBox: {info_hash} (S{season}E{episode})")
            
            add_payload = {
                "magnet": magnet or f"magnet:?xt=urn:btih:{info_hash}",
                "seed": "1", 
                "allow_zip": "false"
            }
            
            # Use data= for form-encoded
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

            if not torrent_id:
                logger.error("Could not determine Torrent ID from TorBox response")
                return None
                
            # 2. Get Torrent Info & Files
            target_torrent = None
            
            # If instant cache, we might get files immediately, but usually need to query list
            # Poll a few times for files to appear if needed
            # "checking" state can take a moment even if cached. Increase retries.
            max_retries = 30
            for attempt in range(max_retries):
                # Log only every 5 attempts or first one to reduce spam
                if attempt == 0 or (attempt + 1) % 5 == 0:
                     logger.info(f"Fetching TorBox list for ID: {torrent_id} (Attempt {attempt+1}/{max_retries})")
                
                list_resp = await self.client.get(f"{self.base_url}/api/torrents/mylist?bypass_cache=true", headers=headers)
                
                if list_resp.status_code == 200:
                    list_data = list_resp.json()
                    if list_data.get("success"):
                        for t in list_data.get("data", []):
                            if str(t.get("id")) == str(torrent_id):
                                target_torrent = t
                                break
                    
                    if target_torrent:
                        state = target_torrent.get("download_state")
                        files = target_torrent.get("files") or []
                        
                        if attempt == 0 or (attempt + 1) % 5 == 0:
                            logger.info(f"Torrent State: {state}, Files: {len(files)}")
                        
                        if files:
                            break
                        elif attempt == 0 or (attempt + 1) % 5 == 0:
                            # Only warn occasionally
                            logger.warning("Torrent found but has no files (hydrating?). Waiting...")
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(2.0)
            
            if not target_torrent:
                logger.error(f"Torrent {torrent_id} added but not found in list.")
                return None
                
            # Find best file
            files = target_torrent.get("files") or []
            if not files:
                 logger.error("No suitable files found in torrent (even after retries)")
                 return None

            # Filter for video files
            video_files = [f for f in files if f.get("name", "").lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm"))]
            
            if not video_files:
                logger.error("No video files found in torrent")
                return None

            best_file_id = None
            
            # SELECTION LOGIC: Season/Episode Matching
            if season is not None and episode is not None:
                import re
                logger.info(f"Looking for S{season:02d}E{episode:02d} in {len(video_files)} files...")
                
                # Regex patterns for S01E01, 1x01, etc.
                # S01E01, S1E1, 1x01, 1x1
                regex_list = [
                    rf"(?i)S{season:02d}E{episode:02d}",
                    rf"(?i)S{season}E{episode}",
                    rf"(?i){season}x{episode:02d}",
                    rf"(?i){season}x{episode}"
                ]
                
                matches = []
                for f in video_files:
                    fname = f.get("name", "")
                    for pat in regex_list:
                        if re.search(pat, fname):
                            matches.append(f)
                            break
                
                if matches:
                    logger.info(f"Found {len(matches)} matching files for S{season}E{episode}")
                    # Pick largest matching file (highest quality)
                    matches.sort(key=lambda x: x.get("size", 0), reverse=True)
                    best_file_id = matches[0].get("id")
                    logger.info(f"Selected file: {matches[0].get('name')}")
                else:
                    logger.warning(f"No file matched S{season}E{episode}. Fallback to largest file.")
            
            # Fallback / Default: Largest File
            if not best_file_id:
                video_files.sort(key=lambda x: x.get("size", 0), reverse=True)
                best_file_id = video_files[0].get("id")
                logger.info(f"Selected largest file (Fallback): {video_files[0].get('name')}")
            
            if not best_file_id:
                 logger.warning("Could not determine best file ID")
                 return None

            # 3. Request Download Link
            try:
                torrent_id_int = int(torrent_id)
                file_id_int = int(best_file_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid ID types - Torrent: {torrent_id}, File: {best_file_id}")
                return None

            link_payload = {
                "token": api_key, 
                "torrent_id": torrent_id_int, 
                "file_id": file_id_int,
                "zip_link": "false" 
            }
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
                
                for attempt in range(30):
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
                        files = target_torrent.get("files") or []
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
            files = target_torrent.get("files") or []
            best_file_id = None
            
            if not files:
                 logger.error("No suitable files found in torrent (even after retries)")
                 return None

            # Debug: Log first file to check structure
            if files:
                logger.info(f"First file sample: {files[0]}")

            # Sort by size desc
            video_files = [f for f in files if f.get("name", "").lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm"))]
            
            if video_files:
                video_files.sort(key=lambda x: x.get("size", 0), reverse=True)
                best_file_id = video_files[0].get("id")
                if not best_file_id:
                     logger.warning(f"Best video file missing ID: {video_files[0]}")
            else:
                 # Fallback to largest file period
                 files.sort(key=lambda x: x.get("size", 0), reverse=True)
                 if files:
                     best_file_id = files[0].get("id")
                     if not best_file_id:
                         logger.warning(f"Fallback file missing ID: {files[0]}")

            # 3. Request Download Link
            # Ensure IDs are integers and token is passed if required by endpoint
            try:
                torrent_id_int = int(torrent_id)
                file_id_int = int(best_file_id)
            except (ValueError, TypeError):
                logger.error(f"Invalid ID types - Torrent: {torrent_id}, File: {best_file_id}")
                return None

            link_payload = {
                "token": api_key, # Explicitly pass token if header isn't enough for this endpoint
                "torrent_id": torrent_id_int, 
                "file_id": file_id_int,
                "zip_link": "false" 
            }
            
            logger.info(f"Requesting DL with payload: {link_payload}")
            
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
