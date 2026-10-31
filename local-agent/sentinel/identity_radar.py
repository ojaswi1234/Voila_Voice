"""
================================================================================
Voila Sentinel - Identity Breach Radar (k-Anonymity)
================================================================================
Capabilities:
1. Strict Mathematical Privacy (k-Anonymity):
   - Computes SHA-1 of credential.
   - Transmits ONLY the first 5 hexadecimal characters of the hash to the public
     HaveIBeenPwned range API (e.g., https://api.pwnedpasswords.com/range/5BAA6).
   - Evaluates whether the remaining 35 characters match completely in local memory.
   - ZERO password bytes, zero plaintext characters, and zero full hashes ever leave the device.
2. Offline 7-Day Caching:
   - Stores range responses in data/hibp_cache.json to prevent network overhead and rate limits.
================================================================================
"""

import os
import sys
import json
import time
import hashlib
import urllib.request
from typing import Dict, List, Any, Optional, Tuple


class IdentityRadar:
    """Evaluates credential exposure in known public breaches using k-Anonymity."""

    def __init__(self, data_dir: Optional[str] = None):
        if not data_dir:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.cache_file = os.path.join(data_dir, "hibp_cache.json")
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass

    def check_pwned_secret(self, secret: str) -> Dict[str, Any]:
        """
        Evaluates whether a secret string appears in known breaches.
        Uses k-Anonymity: only 5 characters of SHA-1 are transmitted.
        """
        if not secret:
            return {"is_breached": False, "breach_count": 0, "message": "Empty string provided"}

        sha1_full = hashlib.sha1(secret.encode("utf-8", errors="ignore")).hexdigest().upper()
        prefix = sha1_full[:5]
        suffix = sha1_full[5:]

        now = time.time()
        cached_entry = self.cache.get(prefix)

        # Check if cache entry is valid (TTL: 7 days = 604800 seconds)
        if cached_entry and (now - cached_entry.get("timestamp", 0) < 604800):
            range_data = cached_entry.get("data", "")
        else:
            url = f"https://api.pwnedpasswords.com/range/{prefix}"
            req = urllib.request.Request(url, headers={"User-Agent": "VoilaSentinel-IdentityRadar/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=6) as resp:
                    range_data = resp.read().decode("utf-8")
                # Save to cache
                self.cache[prefix] = {
                    "timestamp": now,
                    "data": range_data
                }
                self._save_cache()
            except Exception as e:
                # If network fails, check if we have older cached data
                if cached_entry:
                    range_data = cached_entry.get("data", "")
                else:
                    return {
                        "is_breached": False,
                        "breach_count": 0,
                        "sha1_prefix": prefix,
                        "status": "OFFLINE_UNAVAILABLE",
                        "message": f"Could not reach breach radar API: {e}"
                    }

        # Local in-memory matching of the 35-character suffix
        breach_count = 0
        is_breached = False
        for line in range_data.splitlines():
            line_str = line.strip()
            if line_str.startswith(suffix):
                parts = line_str.split(":")
                if len(parts) == 2:
                    try:
                        breach_count = int(parts[1])
                        is_breached = (breach_count > 0)
                    except ValueError:
                        pass
                break

        return {
            "is_breached": is_breached,
            "breach_count": breach_count,
            "sha1_prefix": prefix,
            "k_anonymity_status": "SECURE (Only 5-char prefix transmitted)",
            "risk_verdict": "COMPROMISED_IN_BREACH" if is_breached else "CLEAN"
        }


# Global Singleton
identity_radar = IdentityRadar()
