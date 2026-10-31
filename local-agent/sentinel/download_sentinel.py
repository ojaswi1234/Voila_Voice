"""
================================================================================
Voila Sentinel - Download Folder Sentinel & Ingress Monitor
================================================================================
Capabilities:
1. Scans user Downloads directory for newly arrived executables and scripts.
2. Automatically triggers Static PE & Script Triage on new files.
3. Flags high-entropy or unsigned binaries before user execution.
================================================================================
"""

import os
import sys
import time
from typing import Dict, List, Any, Optional

from .pe_triage import StaticPETriage
from .quarantine_vault import quarantine_vault


class DownloadSentinel:
    """Monitors the Windows user Downloads folder for untrusted binaries."""

    def __init__(self, downloads_dir: Optional[str] = None):
        if not downloads_dir:
            user_profile = os.environ.get("USERPROFILE", "")
            downloads_dir = os.path.join(user_profile, "Downloads")
        self.downloads_dir = downloads_dir

    def scan_downloads(self, auto_quarantine: bool = False) -> Dict[str, Any]:
        """
        Audits all executables and scripts currently in the Downloads folder.
        If auto_quarantine is True, automatically vaults files with verdict == 'HIGH_RISK'.
        """
        if not os.path.exists(self.downloads_dir):
            return {"error": f"Downloads directory not found: {self.downloads_dir}"}

        target_exts = (".exe", ".dll", ".scr", ".sys", ".vbs", ".ps1", ".bat", ".cmd", ".js", ".hta")
        scanned_files = []
        threats_found = []

        for fname in os.listdir(self.downloads_dir):
            fpath = os.path.join(self.downloads_dir, fname)
            if not os.path.isfile(fpath):
                continue

            # Ignore partial browser downloads
            if fname.endswith((".crdownload", ".tmp", ".download", ".part")):
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext in target_exts:
                triage = StaticPETriage.triage_file(fpath)
                scanned_files.append(triage)

                if triage.get("verdict") in ("HIGH_RISK", "SUSPICIOUS"):
                    threat_item = dict(triage)
                    if auto_quarantine and triage.get("verdict") == "HIGH_RISK":
                        q_res = quarantine_vault.quarantine_file(
                            filepath=fpath,
                            reasons=triage.get("indicators", []),
                            threat_score=triage.get("threat_score", 100.0)
                        )
                        threat_item["quarantine_status"] = q_res
                    threats_found.append(threat_item)

        risk_level = "HEALTHY"
        if any(t.get("verdict") == "HIGH_RISK" for t in threats_found):
            risk_level = "CRITICAL"
        elif threats_found:
            risk_level = "WARNING"

        return {
            "risk_level": risk_level,
            "downloads_dir": self.downloads_dir,
            "total_executable_files": len(scanned_files),
            "threats_count": len(threats_found),
            "threats": threats_found,
            "all_scanned": scanned_files
        }


# Global Singleton
download_sentinel = DownloadSentinel()
