"""
================================================================================
Voila Sentinel - Native Win32 System Defense & Emergency IR Controls
================================================================================
Capabilities:
1. Workstation Lockdown: Immediately locks the Windows interactive desktop
   session via Win32 LockWorkStation() upon unauthorized physical or remote intrusion.
2. Emergency Host Network Isolation:
   - Blocks outbound internet connectivity via Windows Firewall rule ("VOILA_SENTINEL_ISOLATION").
   - Preserves local loopback (127.0.0.1) so local services and desktop bridge remain functional.
   - Reversible single-command restoration to lift isolation when containment is resolved.
================================================================================
"""

import os
import sys
import ctypes
import subprocess
from typing import Dict, Any


class SystemDefense:
    """Automates rapid containment, screen lockdown, and host isolation."""

    RULE_NAME = "VOILA_SENTINEL_ISOLATION"

    @classmethod
    def lock_workstation(cls) -> Dict[str, Any]:
        """Immediately locks the Windows desktop session."""
        if sys.platform != "win32":
            return {"status": "UNSUPPORTED", "message": "Workstation locking only supported on Windows"}

        try:
            res = ctypes.windll.user32.LockWorkStation()
            if res != 0:
                return {"status": "SUCCESS", "message": "Workstation successfully locked via Win32 API"}
            else:
                return {"status": "FAILED", "message": "LockWorkStation call returned 0"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Could not lock workstation: {e}"}

    @classmethod
    def is_isolated(cls) -> bool:
        """Checks whether the emergency network isolation firewall rule is currently active."""
        if sys.platform != "win32":
            return False
        try:
            cmd = f'netsh advfirewall firewall show rule name="{cls.RULE_NAME}"'
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return ("VOILA_SENTINEL_ISOLATION" in proc.stdout)
        except Exception:
            return False

    @classmethod
    def isolate_network(cls) -> Dict[str, Any]:
        """
        Activates emergency network isolation:
        Blocks outbound traffic via Windows Firewall rule, severing C2 connections.
        """
        if sys.platform != "win32":
            return {"status": "UNSUPPORTED", "message": "Firewall isolation only supported on Windows"}

        if cls.is_isolated():
            return {"status": "ALREADY_ISOLATED", "message": "Host is already in network isolation state"}

        cmd = (
            f'netsh advfirewall firewall add rule name="{cls.RULE_NAME}" '
            f'dir=out action=block profile=any description="Voila Sentinel Emergency Host Isolation"'
        )
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if proc.returncode == 0 or "Ok." in proc.stdout:
                return {"status": "SUCCESS", "state": "ISOLATED", "message": "Emergency outbound isolation active"}
            else:
                # Need elevated privileges
                return {
                    "status": "ELEVATION_REQUIRED",
                    "message": "Windows Firewall rule creation requires Administrator privileges",
                    "detail": proc.stderr or proc.stdout
                }
        except Exception as e:
            return {"status": "ERROR", "message": f"Failed to execute isolation rule: {e}"}

    @classmethod
    def lift_isolation(cls) -> Dict[str, Any]:
        """Lifts emergency network isolation by deleting the firewall rule."""
        if sys.platform != "win32":
            return {"status": "UNSUPPORTED", "message": "Firewall isolation only supported on Windows"}

        cmd = f'netsh advfirewall firewall delete rule name="{cls.RULE_NAME}"'
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return {"status": "SUCCESS", "state": "NORMAL", "message": "Host network isolation lifted"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Failed to remove isolation rule: {e}"}
