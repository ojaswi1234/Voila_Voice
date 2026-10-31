"""
================================================================================
Voila Sentinel - Persistence & Autoruns Watchdog
================================================================================
Monitors persistence vectors on the Windows workstation:
1. Registry Run & RunOnce keys (HKCU & HKLM).
2. User and System Startup folders.
3. Cryptographic SHA-256 baseline diffing to detect unauthorized additions or tampering.
4. Suspicious path heuristics (executables running from Temp, suspicious script extensions).
================================================================================
"""

import os
import sys
import json
import hashlib
import winreg
from typing import Dict, List, Any, Optional

from .baseline_integrity import BaselineIntegrity


def hash_file_sha256(filepath: str, max_size_mb: int = 50) -> Optional[str]:
    """Computes SHA-256 hash of a file safely with streaming chunks."""
    clean_path = filepath.strip('"').strip("'")
    if not os.path.exists(clean_path) or not os.path.isfile(clean_path):
        return None
    try:
        if os.path.getsize(clean_path) > max_size_mb * 1024 * 1024:
            return "SKIPPED_OVERSIZE"
        hasher = hashlib.sha256()
        with open(clean_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


class PersistenceInspector:
    """Inspects autoruns and compares against a trusted baseline."""

    REG_TARGETS = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU_Run"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU_RunOnce"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM_Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM_RunOnce"),
    ]

    def __init__(self, data_dir: Optional[str] = None):
        if not data_dir:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.baseline_file = os.path.join(data_dir, "persistence_baseline.json")

    def get_startup_directories(self) -> List[str]:
        dirs = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            dirs.append(os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"))
        progdata = os.environ.get("PROGRAMDATA")
        if progdata:
            dirs.append(os.path.join(progdata, r"Microsoft\Windows\Start Menu\Programs\Startup"))
        return [d for d in dirs if os.path.exists(d)]

    def enumerate_current_entries(self) -> List[Dict[str, Any]]:
        entries = []

        # 1. Registry Keys
        for hive, subkey, label in self.REG_TARGETS:
            try:
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ) as k:
                    num_vals = winreg.QueryInfoKey(k)[1]
                    for i in range(num_vals):
                        val_name, val_data, _ = winreg.EnumValue(k, i)
                        # Extract primary binary path from command line
                        cmd = str(val_data).strip()
                        binary_path = ""
                        if cmd.startswith('"'):
                            end_q = cmd.find('"', 1)
                            if end_q != -1:
                                binary_path = cmd[1:end_q]
                            else:
                                binary_path = cmd.strip('"')
                        else:
                            # Handle unquoted paths with spaces (e.g. C:\Program Files\...\app.exe /flag)
                            import re
                            m = re.search(r'^(.*?\.exe)\b', cmd, flags=re.IGNORECASE)
                            if m and os.path.exists(os.path.expandvars(m.group(1))):
                                binary_path = m.group(1)
                            else:
                                binary_path = cmd.split()[0] if cmd else ""
                        binary_path = os.path.expandvars(binary_path)
                        sha256 = hash_file_sha256(binary_path) if os.path.exists(binary_path) else None

                        entries.append({
                            "type": "REGISTRY",
                            "location": label,
                            "name": val_name,
                            "command": cmd,
                            "binary_path": binary_path,
                            "sha256": sha256
                        })
            except Exception:
                pass

        # 2. Startup Folders
        for sdir in self.get_startup_directories():
            try:
                for fname in os.listdir(sdir):
                    fpath = os.path.join(sdir, fname)
                    if os.path.isfile(fpath) and not fname.lower().endswith(".ini"):
                        entries.append({
                            "type": "STARTUP_FOLDER",
                            "location": sdir,
                            "name": fname,
                            "command": fpath,
                            "binary_path": fpath,
                            "sha256": hash_file_sha256(fpath)
                        })
            except Exception:
                pass

        return entries

    def take_baseline(self) -> Dict[str, Any]:
        """Snapshots current entries as the trusted cryptographically sealed baseline."""
        entries = self.enumerate_current_entries()
        baseline_data = {
            "entry_count": len(entries),
            "entries": {f"{e['location']}::{e['name']}": e for e in entries}
        }
        sig = BaselineIntegrity.save_signed_json(self.baseline_file, baseline_data, data_dir=self.data_dir)
        return {"status": "SUCCESS", "baseline_count": len(entries), "signature": sig, "file": self.baseline_file}

    def audit(self) -> Dict[str, Any]:
        """Audits current autoruns, checking against baseline, HMAC signature, and heuristic red flags."""
        current_entries = self.enumerate_current_entries()
        current_map = {f"{e['location']}::{e['name']}": e for e in current_entries}

        baseline_data, integrity_status = BaselineIntegrity.load_signed_json(self.baseline_file, data_dir=self.data_dir)
        has_baseline = (baseline_data is not None)
        baseline_map = baseline_data.get("entries", {}) if baseline_data else {}

        new_entries = []
        modified_entries = []
        suspicious_entries = []

        # Check for baseline tampering
        if integrity_status == "TAMPERED":
            suspicious_entries.append({
                "name": "CRITICAL: Persistence Baseline Cryptographic Signature Mismatch!",
                "location": self.baseline_file,
                "command": "EXTERNAL_TAMPERING_DETECTED",
                "reasons": ["Baseline file HMAC-SHA256 signature mismatch: autoruns baseline was modified externally without authorization."]
            })

        for key, entry in current_map.items():
            cmd_lower = entry["command"].lower()
            reasons = []

            # Heuristics: Flag suspicious persistence locations
            if any(p in cmd_lower for p in (r"\appdata\local\temp", r"\temp\\", r"\public\\")):
                reasons.append("Runs from Temp/Public folder")
            if any(cmd_lower.endswith(ext) for ext in (".vbs", ".js", ".hta", ".bat", ".cmd", ".ps1")):
                reasons.append(f"Script-based autorun ({os.path.splitext(cmd_lower)[1]})")

            if reasons:
                entry_copy = dict(entry)
                entry_copy["reasons"] = reasons
                suspicious_entries.append(entry_copy)

            if has_baseline:
                if key not in baseline_map:
                    new_entries.append(entry)
                else:
                    base_sha = baseline_map[key].get("sha256")
                    cur_sha = entry.get("sha256")
                    if base_sha and cur_sha and base_sha != cur_sha:
                        modified_entries.append({
                            "entry": entry,
                            "baseline_sha256": base_sha,
                            "current_sha256": cur_sha
                        })

        risk_level = "HEALTHY"
        if suspicious_entries or modified_entries:
            risk_level = "WARNING"
        elif new_entries:
            risk_level = "INFO"

        return {
            "risk_level": risk_level,
            "has_baseline": has_baseline,
            "integrity_status": integrity_status,
            "total_current_autoruns": len(current_entries),
            "new_entries_count": len(new_entries),
            "modified_entries_count": len(modified_entries),
            "suspicious_entries_count": len(suspicious_entries),
            "new_entries": new_entries,
            "modified_entries": modified_entries,
            "suspicious_entries": suspicious_entries,
            "all_entries": current_entries
        }
