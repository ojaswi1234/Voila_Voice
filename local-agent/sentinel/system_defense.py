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

    BLOCK_RULE_NAME = "VOILA_SENTINEL_ISOLATION"
    ALLOW_LAN_RULE_NAME = "VOILA_SENTINEL_ISOLATION_LAN_ALLOW"
    RULE_NAME = BLOCK_RULE_NAME

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
            cmd = f'netsh advfirewall firewall show rule name="{cls.BLOCK_RULE_NAME}"'
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return (cls.BLOCK_RULE_NAME in proc.stdout)
        except Exception:
            return False

    @classmethod
    def isolate_network(cls) -> Dict[str, Any]:
        """
        Activates emergency network isolation:
        1. Configures an explicit outbound ALLOW rule for the local subnet & private LAN ranges
           (192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 127.0.0.1) to preserve Mesh Defense with Mobile HUD.
        2. Configures an outbound BLOCK rule for all internet/WAN egress to sever C2 and exfiltration channels.
        """
        if sys.platform != "win32":
            return {"status": "UNSUPPORTED", "message": "Firewall isolation only supported on Windows"}

        if cls.is_isolated():
            return {"status": "ALREADY_ISOLATED", "message": "Host is already in network isolation state"}

        # Step 1: Exempt local LAN mesh so Mobile Emergency HUD can still communicate over Wi-Fi
        cmd_allow_lan = (
            f'netsh advfirewall firewall add rule name="{cls.ALLOW_LAN_RULE_NAME}" '
            f'dir=out action=allow remoteip=LocalSubnet,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,127.0.0.1 '
            f'profile=any description="Voila Sentinel Mesh Defense Local Subnet Exemption"'
        )
        # Step 2: Block general outbound WAN
        cmd_block = (
            f'netsh advfirewall firewall add rule name="{cls.BLOCK_RULE_NAME}" '
            f'dir=out action=block profile=any description="Voila Sentinel Emergency Host Isolation"'
        )
        try:
            # Add LAN allow rule first
            subprocess.run(cmd_allow_lan, shell=True, capture_output=True, text=True)
            # Add general outbound block rule
            proc = subprocess.run(cmd_block, shell=True, capture_output=True, text=True)
            if proc.returncode == 0 or "Ok." in proc.stdout:
                return {
                    "status": "SUCCESS",
                    "state": "ISOLATED",
                    "mesh_lan_preserved": True,
                    "message": "Emergency outbound isolation active (Local LAN Mesh preserved for Mobile HUD)"
                }
            else:
                # Clean up allow rule if block failed
                subprocess.run(f'netsh advfirewall firewall delete rule name="{cls.ALLOW_LAN_RULE_NAME}"', shell=True, capture_output=True)
                return {
                    "status": "ELEVATION_REQUIRED",
                    "message": "Windows Firewall rule creation requires Administrator privileges",
                    "detail": proc.stderr or proc.stdout
                }
        except Exception as e:
            return {"status": "ERROR", "message": f"Failed to execute isolation rule: {e}"}

    @classmethod
    def lift_isolation(cls) -> Dict[str, Any]:
        """Lifts emergency network isolation by deleting both isolation firewall rules."""
        if sys.platform != "win32":
            return {"status": "UNSUPPORTED", "message": "Firewall isolation only supported on Windows"}

        cmd_del_block = f'netsh advfirewall firewall delete rule name="{cls.BLOCK_RULE_NAME}"'
        cmd_del_lan = f'netsh advfirewall firewall delete rule name="{cls.ALLOW_LAN_RULE_NAME}"'
        try:
            subprocess.run(cmd_del_lan, shell=True, capture_output=True, text=True)
            proc = subprocess.run(cmd_del_block, shell=True, capture_output=True, text=True)
            return {"status": "SUCCESS", "state": "NORMAL", "message": "Host network isolation lifted (all rules cleared)"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Failed to remove isolation rule: {e}"}
