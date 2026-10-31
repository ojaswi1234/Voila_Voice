"""
================================================================================
Voila Sentinel - Listening Ports & Wildcard Interface Auditor
================================================================================
Audits local network sockets to detect accidental network exposures:
1. Wildcard (0.0.0.0) dev server bindings (Vite, Next, React, Flask, FastAPI).
2. Unprotected administrative/file sharing ports (SMB 445, RDP 3389).
3. Process-to-port attribution and remediation guidance.
================================================================================
"""

import os
import psutil
from typing import Dict, List, Any


class PortsAuditor:
    """Audits local listening TCP/UDP ports and flags external attack surface exposure."""

    # Common developer server ports that should typically be restricted to 127.0.0.1
    DEV_PORTS = {
        3000: "React / Node Dev Server",
        3001: "Node Dev Server Alt",
        4200: "Angular CLI Dev Server",
        5000: "Flask / ASP.NET Dev Server",
        5173: "Vite / Vue Dev Server",
        8000: "Django / Python SimpleHTTP",
        8080: "Generic Web / Spring Boot Dev Server",
        8081: "Metro Bundler / React Native",
        8888: "Jupyter Notebook Server",
        9000: "PHP-FPM / SonarQube",
    }

    # High-risk management or legacy protocols
    HIGH_RISK_PORTS = {
        135: "RPC Endpoint Mapper",
        139: "NetBIOS Session Service",
        445: "SMB File Sharing",
        3389: "Remote Desktop Protocol (RDP)",
        5985: "Windows Remote Management (WinRM HTTP)",
        5986: "Windows Remote Management (WinRM HTTPS)",
    }

    @classmethod
    def audit(cls) -> Dict[str, Any]:
        """Performs a fast, non-intrusive scan of all listening sockets."""
        listening_ports = []
        exposed_dev_servers = []
        exposed_high_risk = []
        safe_localhost = []

        try:
            connections = psutil.net_connections(kind="inet")
        except Exception as e:
            return {"error": f"Failed to query network connections: {e}", "listening": []}

        for conn in connections:
            if conn.status != psutil.CONN_LISTEN:
                continue

            ip, port = conn.laddr
            pid = conn.pid
            pname = "Unknown"
            exe_path = ""

            if pid:
                try:
                    p = psutil.Process(pid)
                    pname = p.name()
                    exe_path = p.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            is_wildcard = (ip in ("0.0.0.0", "::"))
            is_localhost = (ip in ("127.0.0.1", "::1", "localhost"))

            item = {
                "ip": ip,
                "port": port,
                "pid": pid,
                "process_name": pname,
                "exe_path": exe_path,
                "is_wildcard": is_wildcard,
                "is_localhost": is_localhost,
                "service_description": cls.DEV_PORTS.get(port) or cls.HIGH_RISK_PORTS.get(port, "General Service")
            }
            listening_ports.append(item)

            if is_wildcard:
                if port in cls.DEV_PORTS:
                    exposed_dev_servers.append(item)
                elif port in cls.HIGH_RISK_PORTS:
                    # Distinguish standard Windows System core listener from rogue service
                    if pname.lower() in ("system", "svchost.exe") and port in (135, 139, 445):
                        item["service_description"] += " (Windows Core - Verify Firewall Profile)"
                        # Keep as warning rather than critical alert for default Windows system daemons
                    else:
                        exposed_high_risk.append(item)
            elif is_localhost:
                safe_localhost.append(item)

        # Risk assessment
        risk_level = "HEALTHY"
        if exposed_high_risk:
            risk_level = "CRITICAL"
        elif exposed_dev_servers:
            risk_level = "WARNING"

        return {
            "risk_level": risk_level,
            "total_listening": len(listening_ports),
            "total_wildcard": sum(1 for p in listening_ports if p["is_wildcard"]),
            "total_localhost": len(safe_localhost),
            "exposed_dev_servers": exposed_dev_servers,
            "exposed_high_risk": exposed_high_risk,
            "all_listening": listening_ports
        }
