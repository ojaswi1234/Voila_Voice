"""
================================================================================
Voila Sentinel - Core Threat Posture Aggregator & Incident Evaluator
================================================================================
Combines:
1. Process Watchdog (Behavioral cmdline & shell tracking)
2. Ports Auditor (0.0.0.0 wildcard & dev server leakage)
3. Persistence Inspector (Registry & Startup autorun baseline diffing)
Produces a unified threat posture score and plain-English actionable briefings.
================================================================================
"""

import os
import time
from typing import Dict, Any, List

from .ports_auditor import PortsAuditor
from .process_watchdog import ProcessWatchdog
from .persistence_inspector import PersistenceInspector
from .lan_guardian import lan_guardian
from .secret_scanner import secret_scanner
from .identity_radar import identity_radar


class SentinelCore:
    """Central engine orchestrating host telemetry and posture evaluations."""

    def __init__(self, data_dir: str = None):
        if not data_dir:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.persistence_inspector = PersistenceInspector(data_dir=data_dir)

    def evaluate_host_posture(self, workspace_path: str = None) -> Dict[str, Any]:
        """Runs a complete host sweep and calculates security posture."""
        t0 = time.time()

        ports_result = PortsAuditor.audit()
        process_result = ProcessWatchdog.scan()
        persist_result = self.persistence_inspector.audit()
        lan_result = lan_guardian.scan_local_devices()

        # Workspace Secret Sweep
        if not workspace_path:
            workspace_path = os.getcwd()
        secrets_result = secret_scanner.scan_directory(workspace_path, max_files=150)

        elapsed_ms = (time.time() - t0) * 1000.0

        # Calculate Posture Score (100 is pristine)
        score = 100.0
        findings = []

        # 1. Evaluate Ports
        if ports_result.get("exposed_high_risk"):
            score -= 35.0
            for p in ports_result["exposed_high_risk"]:
                findings.append(f"CRITICAL: High-risk port {p['port']} ({p['service_description']}) exposed to 0.0.0.0 by {p['process_name']}.")

        if ports_result.get("exposed_dev_servers"):
            score -= (len(ports_result["exposed_dev_servers"]) * 10.0)
            for p in ports_result["exposed_dev_servers"]:
                findings.append(f"WARNING: Development server port {p['port']} ({p['service_description']}) exposed to local network via 0.0.0.0 (Process: {p['process_name']}).")

        # 2. Evaluate Processes
        for a in process_result.get("anomalies", []):
            if a["severity"] == "CRITICAL":
                score -= 30.0
                findings.append(f"CRITICAL: Anomaly on PID {a['pid']} ({a['process_name']}): {', '.join(a['reasons'])}.")
            elif a["severity"] == "HIGH":
                score -= 20.0
                findings.append(f"WARNING: Suspicious flag on PID {a['pid']} ({a['process_name']}): {', '.join(a['reasons'])}.")
            elif a["severity"] == "MEDIUM":
                score -= 8.0
                findings.append(f"NOTICE: Elevated entropy/hidden window on PID {a['pid']} ({a['process_name']}): {', '.join(a['reasons'])}.")

        # 3. Evaluate Persistence
        for s in persist_result.get("suspicious_entries", []):
            score -= 15.0
            findings.append(f"WARNING: Suspicious autorun entry '{s['name']}': {', '.join(s['reasons'])}.")

        for m in persist_result.get("modified_entries", []):
            score -= 20.0
            findings.append(f"WARNING: Modified startup binary '{m['entry']['name']}' (Hash mismatch against baseline).")

        if persist_result.get("new_entries_count", 0) > 0 and persist_result.get("has_baseline"):
            score -= min(10.0, persist_result["new_entries_count"] * 2.0)
            findings.append(f"NOTICE: Detected {persist_result['new_entries_count']} new startup items added since baseline.")

        # 4. Evaluate LAN & Gateway Integrity (Anti-MITM)
        gw = lan_result.get("gateway", {})
        if gw.get("is_spoofed"):
            score -= 45.0
            for r in gw.get("reasons", []):
                findings.append(r)

        # 5. Evaluate Workspace Secrets Exposure
        for s in secrets_result.get("findings", []):
            if s["severity"] == "CRITICAL":
                score -= 25.0
                findings.append(f"CRITICAL: Exposed {s['type']} in {os.path.basename(s['source'])} (Line {s['line']}: {s['masked']}).")
            elif s["severity"] == "HIGH":
                score -= 15.0
                findings.append(f"WARNING: Exposed {s['type']} in {os.path.basename(s['source'])} (Line {s['line']}: {s['masked']}).")

        score = max(0.0, min(100.0, score))

        if score >= 90.0:
            status = "HEALTHY"
        elif score >= 70.0:
            status = "ATTENTION_REQUIRED"
        else:
            status = "CRITICAL_EXPOSURE"

        # Generate Conversational Executive Summary
        if not findings:
            summary = "Your workstation security posture is pristine. No suspicious processes, autoruns, or exposed developer ports detected."
        else:
            summary = f"Security Posture: {status} ({score:.0f}/100). Found {len(findings)} telemetry observation(s) requiring attention."

        return {
            "status": status,
            "posture_score": round(score, 1),
            "scan_duration_ms": round(elapsed_ms, 1),
            "executive_summary": summary,
            "findings_count": len(findings),
            "findings": findings,
            "telemetry": {
                "ports": ports_result,
                "processes": process_result,
                "persistence": persist_result,
                "network": lan_result,
                "secrets": secrets_result
            }
        }


# Global Singleton
sentinel_core = SentinelCore()
