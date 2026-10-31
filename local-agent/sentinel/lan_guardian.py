"""
================================================================================
Voila Sentinel - Passive LAN Guardian & Gateway ARP Integrity Monitor
================================================================================
Capabilities:
1. 100% Passive Subnet Asset Discovery (zero packet floods, zero port sweeps).
2. Gateway ARP Integrity Verification: Detects ARP Cache Poisoning / Man-In-The-Middle
   attacks (Ettercap, Cain & Abel, rogue hotspot evil-twin spoofing).
3. Offline Hardware Vendor (OUI) Fingerprinting (Apple, Samsung, Intel, TP-Link, etc.).
4. Known Devices Baseline Tracking: Detects new or rogue MAC addresses on the subnet.
================================================================================
"""

import os
import sys
import json
import re
import time
import subprocess
from typing import Dict, List, Any, Optional, Tuple


class LANGuardian:
    """Passive local area network monitor and anti-spoofing sentinel."""

    def __init__(self, data_dir: Optional[str] = None):
        if not data_dir:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.oui_file = os.path.join(data_dir, "oui_vendors.json")
        self.baseline_file = os.path.join(data_dir, "network_baseline.json")
        self.oui_db = self._load_oui_db()

    def _load_oui_db(self) -> Dict[str, str]:
        if os.path.exists(self.oui_file):
            try:
                with open(self.oui_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def resolve_vendor(self, mac: str) -> str:
        """Resolves MAC address (format xx-xx-xx-xx-xx-xx or xx:xx:xx:xx:xx:xx) to hardware vendor."""
        if not mac:
            return "Unknown"
        normalized = mac.replace("-", ":").lower()
        parts = normalized.split(":")
        if len(parts) >= 3:
            prefix = ":".join(parts[:3])
            return self.oui_db.get(prefix, "Unregistered / Generic Hardware")
        return "Unknown"

    def get_active_network_info(self) -> Dict[str, Any]:
        """Passively queries netsh to determine active interface, local IP, and default gateway."""
        active_adapter = "Unknown"
        local_ip = "127.0.0.1"
        gateway_ip = None

        try:
            res = subprocess.run(["netsh", "interface", "ipv4", "show", "config"], capture_output=True, text=True, timeout=5)
            lines = res.stdout.splitlines()
            cur_interface = ""
            for line in lines:
                line_str = line.strip()
                if "Configuration for interface" in line_str:
                    m = re.search(r'Configuration for interface "(.*?)"', line_str)
                    if m:
                        cur_interface = m.group(1)
                elif "IP Address:" in line_str:
                    parts = line_str.split(":", 1)
                    if len(parts) == 2:
                        ip = parts[1].strip()
                        if not ip.startswith("127.") and not ip.startswith("169.254."):
                            local_ip = ip
                            active_adapter = cur_interface
                elif "Default Gateway:" in line_str:
                    parts = line_str.split(":", 1)
                    if len(parts) == 2:
                        gw = parts[1].strip()
                        if gw and gw != "None" and not gw.startswith("0."):
                            gateway_ip = gw
        except Exception:
            pass

        return {
            "adapter": active_adapter,
            "local_ip": local_ip,
            "gateway_ip": gateway_ip
        }

    def parse_kernel_arp_table(self) -> List[Dict[str, Any]]:
        """Passively reads the Windows kernel ARP table without injecting network traffic."""
        devices = []
        try:
            res = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
            lines = res.stdout.splitlines()

            cur_iface = ""
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue

                if line_str.startswith("Interface:"):
                    m = re.search(r'Interface:\s*([0-9.]+)', line_str)
                    if m:
                        cur_iface = m.group(1)
                    continue

                # Match IP MAC Type line: e.g. 172.22.120.1  f8-c1-16-45-b5-80  dynamic
                match = re.search(r'^([0-9.]+)\s+([0-9a-fA-F-]+)\s+([a-zA-Z]+)', line_str)
                if match:
                    ip = match.group(1)
                    mac = match.group(2).lower()
                    entry_type = match.group(3).lower()

                    # Filter out standard broadcast and multicast entries
                    if mac in ("ff-ff-ff-ff-ff-ff", "01-00-5e-00-00-16", "01-00-5e-00-00-fb", "01-00-5e-00-00-fc", "01-00-5e-7f-ff-fa"):
                        continue
                    if ip.startswith("224.") or ip.startswith("239.") or ip.endswith(".255"):
                        continue

                    devices.append({
                        "ip": ip,
                        "mac": mac,
                        "type": entry_type,
                        "interface_ip": cur_iface,
                        "vendor": self.resolve_vendor(mac)
                    })
        except Exception:
            pass

        return devices

    def audit_gateway(self) -> Dict[str, Any]:
        """
        Verifies default gateway ARP integrity against spoofing / poisoning.
        """
        net_info = self.get_active_network_info()
        gateway_ip = net_info.get("gateway_ip")
        if not gateway_ip:
            return {"status": "UNKNOWN", "message": "No active default gateway detected (offline or disconnected)."}

        arp_devices = self.parse_kernel_arp_table()
        cur_gw_mac = None
        for dev in arp_devices:
            if dev["ip"] == gateway_ip:
                cur_gw_mac = dev["mac"]
                break

        if not cur_gw_mac:
            return {
                "status": "NOTICE",
                "gateway_ip": gateway_ip,
                "message": "Gateway IP is not yet populated in the local ARP cache."
            }

        # Check against baseline
        has_baseline = os.path.exists(self.baseline_file)
        baseline_data = {}
        if has_baseline:
            try:
                with open(self.baseline_file, "r", encoding="utf-8") as f:
                    baseline_data = json.load(f)
            except Exception:
                has_baseline = False

        base_gw_ip = baseline_data.get("gateway_ip")
        base_gw_mac = baseline_data.get("gateway_mac")

        spoofing_detected = False
        reasons = []

        if has_baseline and base_gw_ip == gateway_ip:
            if base_gw_mac and base_gw_mac != cur_gw_mac:
                spoofing_detected = True
                reasons.append(
                    f"CRITICAL: Gateway MAC mismatch! Known gateway '{base_gw_mac}' was replaced by '{cur_gw_mac}' on IP {gateway_ip}. Potential ARP Poisoning / MITM attack!"
                )

        status = "CRITICAL_SPOOFING" if spoofing_detected else "VERIFIED"

        return {
            "status": status,
            "gateway_ip": gateway_ip,
            "gateway_mac": cur_gw_mac,
            "gateway_vendor": self.resolve_vendor(cur_gw_mac),
            "is_spoofed": spoofing_detected,
            "has_baseline": has_baseline,
            "baseline_gateway_mac": base_gw_mac,
            "reasons": reasons
        }

    def scan_local_devices(self) -> Dict[str, Any]:
        """Audits all active devices discovered on the local subnet."""
        t0 = time.time()
        net_info = self.get_active_network_info()
        devices = self.parse_kernel_arp_table()
        gw_audit = self.audit_gateway()

        # Check known devices baseline
        has_baseline = os.path.exists(self.baseline_file)
        known_macs = set()
        if has_baseline:
            try:
                with open(self.baseline_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    known_macs = set(data.get("known_macs", []))
            except Exception:
                pass

        new_devices = []
        for d in devices:
            is_new = (has_baseline and d["mac"] not in known_macs)
            d["is_new_to_network"] = is_new
            if is_new:
                new_devices.append(d)

        elapsed_ms = (time.time() - t0) * 1000.0

        risk_level = "HEALTHY"
        if gw_audit.get("is_spoofed"):
            risk_level = "CRITICAL"
        elif new_devices:
            risk_level = "INFO"

        return {
            "risk_level": risk_level,
            "scan_duration_ms": round(elapsed_ms, 1),
            "active_adapter": net_info.get("adapter"),
            "local_ip": net_info.get("local_ip"),
            "gateway": gw_audit,
            "total_subnet_devices": len(devices),
            "new_devices_count": len(new_devices),
            "new_devices": new_devices,
            "devices": devices
        }

    def take_network_baseline(self) -> Dict[str, Any]:
        """Snapshots current gateway and active subnet devices as trusted baseline."""
        net_info = self.get_active_network_info()
        devices = self.parse_kernel_arp_table()
        gw_audit = self.audit_gateway()

        baseline_data = {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "adapter": net_info.get("adapter"),
            "local_ip": net_info.get("local_ip"),
            "gateway_ip": net_info.get("gateway_ip"),
            "gateway_mac": gw_audit.get("gateway_mac"),
            "known_macs": [d["mac"] for d in devices],
            "devices_snapshot": devices
        }

        with open(self.baseline_file, "w", encoding="utf-8") as f:
            json.dump(baseline_data, f, indent=2)

        return {
            "status": "SUCCESS",
            "gateway_ip": net_info.get("gateway_ip"),
            "gateway_mac": gw_audit.get("gateway_mac"),
            "devices_count": len(devices),
            "baseline_file": self.baseline_file
        }


# Global Singleton
lan_guardian = LANGuardian()
