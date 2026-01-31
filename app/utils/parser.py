import re
from typing import List, Dict, Any

class VideoParser:
    @staticmethod
    def get_quality(filename: str) -> str:
        filename = filename.lower()
        if any(x in filename for x in ["2160p", "4k", "uhd"]):
            return "4K"
        if "1080p" in filename:
            return "1080p"
        if "720p" in filename:
            return "720p"
        if "480p" in filename:
            return "480p"
        return "Unknown"

    @staticmethod
    def get_codecs(filename: str) -> List[str]:
        filename = filename.lower()
        codecs = []
        if any(x in filename for x in ["hevc", "h265", "x265"]):
            codecs.append("hevc")
        if any(x in filename for x in ["av1"]):
            codecs.append("av1")
        if any(x in filename for x in ["h264", "x264", "avc"]):
            codecs.append("h264")
        return codecs

    @staticmethod
    def get_audio(filename: str) -> List[str]:
        filename = filename.lower()
        audio = []
        if any(x in filename for x in ["atmos"]):
            audio.append("atmos")
        if any(x in filename for x in ["dts-hd", "dts:x", "dtsx"]):
            audio.append("dts-x")
        if any(x in filename for x in ["truehd"]):
            audio.append("truehd")
        if any(x in filename for x in ["eac3", "ddp", "dd+", "dolby digital plus"]):
            audio.append("eac3")
        if any(x in filename for x in ["ac3", "dd5.1"]):
            audio.append("ac3")
        if any(x in filename for x in ["aac"]):
            audio.append("aac")
        return audio
        
    @staticmethod
    def get_hdr(filename: str) -> List[str]:
        filename = filename.lower()
        hdr = []
        if any(x in filename for x in ["dv", "dovi", "dolby vision"]):
            hdr.append("dolby_vision")
        if any(x in filename for x in ["hdr10+", "hdr10plus"]):
            hdr.append("hdr10+")
        elif any(x in filename for x in ["hdr", "hdr10"]): # check hdr after hdr10+
            hdr.append("hdr10")
        return hdr

    @staticmethod
    def get_source(filename: str) -> str:
        filename = filename.lower()
        if any(x in filename for x in ["remux", "bdremux"]):
            return "remux"
        if any(x in filename for x in ["bluray", "bdrip", "brrip"]):
            return "bluray"
        if any(x in filename for x in ["webdl", "web-dl", "webrip", "hbo", "amzn", "nf"]):
            return "web"
        if any(x in filename for x in ["hdtv"]):
            return "hdtv"
        if any(x in filename for x in ["cam", "ts", "telesync", "camrip"]):
            return "cam"
        return "unknown"

    @staticmethod
    def get_release_group(filename: str) -> str:
        # Regex to find group at end of filename: "-Group" or "-Group.mkv"
        # Avoids common false positives like "-2160p" or "-10bit"
        try:
            match = re.search(r'-([a-zA-Z0-9]+)(?:\.[a-z0-9]{3,4})?$', filename)
            if match:
                group = match.group(1)
                # Filter out technical terms that might look like groups
                if group.lower() not in ["264", "265", "hevc", "10bit", "hdr", 
                                       "remux", "4k", "1080p", "720p", "webdl", "bluray"]:
                    return group
        except:
            pass
        return ""

    @staticmethod
    def score_file(filename: str, size_bytes: int = 0, 
                  exclude_hevc: bool = False,
                  exclude_eac3: bool = False,
                  exclude_dolby_vision: bool = False) -> int:
        
        filename = filename.lower()
        score = 0
        
        # --- HARD FILTERS (Negative Infantry) ---
        # Immediate huge penalty for excluded items
        if exclude_hevc and any(x in filename for x in ["hevc", "h265", "x265"]):
            return -1000
        if exclude_eac3 and any(x in filename for x in ["eac3", "ddp", "dd+", "atmos"]):
            return -1000
        if exclude_dolby_vision and any(x in filename for x in ["dv", "dovi", "dolby vision", "hdr10+"]):
            return -1000
            
        # Filter Garbage
        if any(x in filename for x in ["cam", "ts", "telesync", "camrip", "sample"]):
            return -500
            
        # --- BASE QUALITY SCORE ---
        quality = VideoParser.get_quality(filename)
        if quality == "4K": score += 200
        elif quality == "1080p": score += 100
        elif quality == "720p": score += 50
        
        # --- SOURCE SCORE ---
        source = VideoParser.get_source(filename)
        if source == "remux": score += 100
        elif source == "bluray": score += 80
        elif source == "web": score += 50
        
        # --- AUDIO SCORE ---
        # Prefer higher quality audio usually
        audio = VideoParser.get_audio(filename)
        if "atmos" in audio or "truehd" in audio or "dts-x" in audio:
            score += 40
        elif "eac3" in audio:
            score += 20
            
        # --- HDR SCORE ---
        hdr = VideoParser.get_hdr(filename)
        if "dolby_vision" in hdr: score += 50
        if "hdr10" in hdr or "hdr10+" in hdr: score += 30
        
        # --- SIZE FACTOR ---
        # Prefer larger files (within reason) as proxy for bitrate
        # +1 point per GB, max 50 points
        gb_size = size_bytes / (1024*1024*1024)
        score += min(int(gb_size), 50)
        
        return score
