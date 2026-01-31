import httpx
import asyncio
import re
from loguru import logger
from typing import Optional, Dict
from app.services.base import DebridClient
from app.utils.parser import VideoParser

class RealDebridService(DebridClient):
    """
    Client for Real-Debrid API.
    Docs: https://api.real-debrid.com/
    """
    def __init__(self):
        self.base_url = "https://api.real-debrid.com/rest/1.0"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def _get_headers(self, api_key: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    async def _get_cached_file_ids(self, info_hash: str, api_key: str) -> Optional[set]:
        try:
            headers = await self._get_headers(api_key)
            resp = await self.client.get(f"{self.base_url}/torrents/instantAvailability/{info_hash}", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # Structure: { hash: { "rd": [ {"1":{...}, "2":{...}}, ... ] } }
                if info_hash.lower() in data:
                    rd_data = data[info_hash.lower()].get("rd", [])
                    cached_ids = set()
                    for variant in rd_data:
                        cached_ids.update(variant.keys())
                    return cached_ids
        except Exception as e:
            logger.error(f"Error checking instant availability: {e}")
        return None

    async def resolve_stream(
        self, 
        source_id: str, 
        info_hash: str, 
        magnet: str, 
        api_key: str, 
        season: Optional[int] = None, 
        episode: Optional[int] = None,
        exclude_hevc: bool = False,
        exclude_eac3: bool = False,
        exclude_dolby_vision: bool = False
    ) -> Optional[str]:
        """
        Resolves a Real-Debrid stream.
        1. Add Magnet -> Get Torrent ID
        2. Poll Info -> Wait for file list (or check if cached)
        3. Match File (SxxExx)
        4. Select File (Trigger conversion if needed)
        5. Unrestrict Link
        """
        if not api_key:
            logger.error("No RealDebrid API Key provided")
            return None

        headers = await self._get_headers(api_key)
        
        # 1. Check Instant Availability (Pre-Check)
        # We fetch this to ensure we only select files that are ACTUALLY cached.
        cached_file_ids = await self._get_cached_file_ids(info_hash, api_key)
        if cached_file_ids:
            logger.info(f"Found {len(cached_file_ids)} instantly available file IDs for {info_hash}")
        else:
             logger.warning(f"No instant availability found for {info_hash}. Selection might trigger download.")

        # 2. Add Magnet
        logger.info(f"Adding magnet to RD: {info_hash} (S{season}E{episode})")
        
        # RD 'addMagnet' takes 'magnet' form param
        magnet_link = magnet or f"magnet:?xt=urn:btih:{info_hash}"
        resp = await self.client.post(f"{self.base_url}/torrents/addMagnet", data={"magnet": magnet_link}, headers=headers)
        
        if resp.status_code not in [200, 201]:
             logger.error(f"RD Add Failed: {resp.text}")
             return None
             
        data = resp.json()
        torrent_id = data.get("id")
        if not torrent_id:
             logger.error("RD did not return torrent ID")
             return None

        # 2. Poll for Info (Files)
        # Even if allowed, we need file list to pick correct episode
        
        selected_file_id = None
        target_torrent = None
        
        # Poll briefly to get file list
        for attempt in range(15):
            info_resp = await self.client.get(f"{self.base_url}/torrents/info/{torrent_id}", headers=headers)
            if info_resp.status_code == 200:
                target_torrent = info_resp.json()
                status = target_torrent.get("status")
                files = target_torrent.get("files", [])
                
                # "waiting_selection" means files are ready to be picked
                # "downloaded" means it's done (if we selected all?)
                if files:
                    logger.info(f"RD Torrent Status: {status}, Files: {len(files)}")
                    break
            
            await asyncio.sleep(1.0)
            
        if not target_torrent:
            logger.error("Failed to get torrent info from RD")
            return None
            
        files = target_torrent.get("files", [])
        if not files:
             logger.error("No files found in RD torrent")
             return None

        # 3. Find Best File (Regex Match)
        # RD File Object: {'id': 1, 'path': '/...mkv', 'bytes': 1234, 'selected': 0}
        
        video_files = [f for f in files if f.get("path", "").lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm"))]
        

        if not video_files:
            logger.error("No video files in RD torrent")
            return None

        # --- SCORE & FILTER FILES (Phase 2) ---
        ranked_files = []
        for f in video_files:
            score = VideoParser.score_file(
                filename=f.get("path", ""), 
                size_bytes=f.get("bytes", 0),
                exclude_hevc=exclude_hevc,
                exclude_eac3=exclude_eac3,
                exclude_eac3=exclude_eac3,
                exclude_dolby_vision=exclude_dolby_vision
            )
            
            # --- CHECK INSTANT AVAILABILITY ---
            # Penalize files not in instant cache to prevent "Torrent is downloading" error
            if cached_file_ids is not None:
                # RD file IDs are ints in the file list but strings in availability keys usually
                fid = str(f.get("id"))
                if fid not in cached_file_ids:
                    score = -2000 # Massive penalty for non-cached files
            
            # Filter out files with Hard Exclusion penalty (-1000)
            if score > -900: 
                f["_score"] = score
                ranked_files.append(f)
        
        # Sort by Score Descending
        ranked_files.sort(key=lambda x: x["_score"], reverse=True)
        
        if ranked_files:
             logger.info(f"Scored & Ranked {len(ranked_files)} files. Top: {ranked_files[0]['path']} (Score: {ranked_files[0]['_score']})")
             video_files = ranked_files
        else:
             logger.warning("All files filtered out by restrictions! Falling back to all files (sorted by size).")
             # Fallback: Sort original by size
             video_files.sort(key=lambda x: x.get("bytes", 0), reverse=True)

        best_file_id = None
        
        # SELECTION LOGIC: Season/Episode Matching
        if season is not None and episode is not None:
            logger.info(f"Looking for S{season:02d}E{episode:02d} in {len(video_files)} files...")
            
            # Regex patterns for S01E01, 1x01, etc.
            regex_list = [
                rf"(?i)S{season:02d}E{episode:02d}",
                rf"(?i)S{season}E{episode}",
                rf"(?i){season}x{episode:02d}",
                rf"(?i){season}x{episode}"
            ]
            
            # Since video_files is already sorted by score (or size fallback),
            # the first match we find is the "Best" match.
            for f in video_files:
                fname = f.get("path", "")
                for pat in regex_list:
                    if re.search(pat, fname):
                        best_file_id = f.get("id")
                        logger.info(f"Selected RD file (Score: {f.get('_score', 'N/A')}): {f.get('path')}")
                        break
                if best_file_id:
                    break
            
            if not best_file_id:
                logger.warning(f"No match for S{season}E{episode}. Fallback to highest scored file.")

        # Fallback (or Movie selection)
        if not best_file_id:
            # video_files is already sorted by score
            best_file_id = video_files[0].get("id")
            logger.info(f"Selected highest scored file (Fallback): {video_files[0].get('path')}")



        if not best_file_id:
            return None

        # 4. Select File (if waiting selection)
        if target_torrent.get("status") == "waiting_files_selection":
            logger.info(f"Selecting file {best_file_id} on RD...")
            sel_resp = await self.client.post(f"{self.base_url}/torrents/selectFiles/{torrent_id}", data={"files": str(best_file_id)}, headers=headers)
            if sel_resp.status_code not in [200, 204]:
                 logger.error(f"RD Selection Failed: {sel_resp.text}")
                 return None
        
        # 5. Get Download Link
        # Only if status is 'downloaded' (instant cache) or 'downloading' (if active).
        # We need to fetch info again to get the 'links' list
        # We need the link that corresponds to our file.
        
        # Re-fetch info to get generated links
        final_link = None
        for attempt in range(10):
            info_resp = await self.client.get(f"{self.base_url}/torrents/info/{torrent_id}", headers=headers)
            if info_resp.status_code == 200:
                target_torrent = info_resp.json()
                status = target_torrent.get("status")
                links = target_torrent.get("links", [])
                
                if status == "downloaded" and links:
                    # If we selected ONE file, there should be ONE link (usually).
                    # If multi, RD usually maps them order-wise but it's tricky.
                    # For simplicty, if we only selected one file, take the first link.
                    # Or check valid links.
                    if len(links) >= 1:
                        # We need to UNRESTRICT this link
                        final_link = links[0] # Naive but works for single file selection
                        break
                elif status == "downloading":
                     # Not cached instantly?
                     logger.warning("Torrent is downloading (not cached). Cannot stream instantly.")
                     return None
            
            await asyncio.sleep(1.0)

        if not final_link:
            logger.error("RD did not generate a download link (not cached?)")
            return None

        # 6. Unrestrict the Link
        logger.info(f"Unrestricting link: {final_link}")
        unrestrict_resp = await self.client.post(f"{self.base_url}/unrestrict/link", data={"link": final_link}, headers=headers)
        
        if unrestrict_resp.status_code == 200:
            unr_data = unrestrict_resp.json()
            stream_url = unr_data.get("download")
            return stream_url
        else:
            logger.error(f"RD Unrestrict Failed: {unrestrict_resp.text}")
            return None
