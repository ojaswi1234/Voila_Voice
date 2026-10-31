"""
================================================================================
Voila Sentinel CLI - Endpoint Telemetry Command Interface
================================================================================
Commands:
  status             - Complete posture sweep (Ports + Processes + Persistence)
  audit-ports        - Audits listening TCP/UDP sockets for wildcard/dev-server leakage
  scan-processes     - Inspects active process tree for obfuscated & suspicious commands
  audit-persistence  - Audits Registry Run keys and Startup folder against baseline
  take-baseline      - Captures current autoruns as trusted baseline
================================================================================
"""

import os
import sys
import json
import argparse

# Ensure console supports UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure local-agent directory is on path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from sentinel.sentinel_core import sentinel_core
from sentinel.ports_auditor import PortsAuditor
from sentinel.process_watchdog import ProcessWatchdog
from sentinel.persistence_inspector import PersistenceInspector


def print_banner():
    print("""
+-------------------------------------------------------------+
|          VOILA SENTINEL - PERSONAL CYBER DEFENSE            |
|                 Endpoint Telemetry Core                     |
+-------------------------------------------------------------+
    """)


def main():
    parser = argparse.ArgumentParser(description="Voila Sentinel Endpoint Telemetry CLI")
    parser.add_argument("command", choices=["status", "audit-ports", "scan-processes", "audit-persistence", "take-baseline"],
                        help="Telemetry command to execute")
    parser.add_argument("--json", action="store_true", help="Output results in raw JSON format")

    args = parser.parse_args()

    if args.command == "status":
        result = sentinel_core.evaluate_host_posture()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            score = result["posture_score"]
            status = result["status"]
            print(f"Status: {status} | Posture Score: {score}/100 | Scan Duration: {result['scan_duration_ms']}ms")
            print(f"\nExecutive Summary:\n  {result['executive_summary']}\n")
            if result["findings"]:
                print("Detailed Observations:")
                for f in result["findings"]:
                    print(f"  - {f}")
            else:
                print("[OK] No security anomalies detected on the endpoint.")

    elif args.command == "audit-ports":
        result = PortsAuditor.audit()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Risk Level: {result['risk_level']} | Total Listening: {result['total_listening']} | Wildcard (0.0.0.0): {result['total_wildcard']}")
            if result["exposed_dev_servers"]:
                print("\n[!] Exposed Dev Servers:")
                for p in result["exposed_dev_servers"]:
                    print(f"  - Port {p['port']} ({p['service_description']}) bound to 0.0.0.0 by {p['process_name']} (PID {p['pid']})")
            if result["exposed_high_risk"]:
                print("\n[CRITICAL] High-Risk Ports Exposed:")
                for p in result["exposed_high_risk"]:
                    print(f"  - Port {p['port']} ({p['service_description']}) bound to 0.0.0.0 by {p['process_name']} (PID {p['pid']})")
            if not result["exposed_dev_servers"] and not result["exposed_high_risk"]:
                print("\n[OK] All developer and management ports are safely isolated.")

    elif args.command == "scan-processes":
        result = ProcessWatchdog.scan()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Risk Level: {result['risk_level']} | Checked Processes: {result['total_processes_checked']} | Anomalies: {result['total_anomalies']}")
            if result["anomalies"]:
                print("\n[!] Process Anomalies Detected:")
                for a in result["anomalies"]:
                    print(f"  - [{a['severity']}] PID {a['pid']} ({a['process_name']}): {', '.join(a['reasons'])}")
                    print(f"    Cmdline: {a['cmdline']}")
            else:
                print("\n[OK] All active process command lines passed static and entropy behavioral checks.")

    elif args.command == "audit-persistence":
        inspector = PersistenceInspector()
        result = inspector.audit()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Risk Level: {result['risk_level']} | Total Autoruns: {result['total_current_autoruns']} | Has Baseline: {result['has_baseline']}")
            if result["suspicious_entries"]:
                print("\n[!] Suspicious Autorun Locations:")
                for s in result["suspicious_entries"]:
                    print(f"  - {s['name']} ({s['location']}): {', '.join(s['reasons'])}")
            if result["new_entries"]:
                print(f"\n[+] New Entries Added Since Baseline ({len(result['new_entries'])}):")
                for n in result["new_entries"][:5]:
                    print(f"  - {n['name']} ({n['location']})")
            if not result["suspicious_entries"] and not result["new_entries"]:
                print("\n[OK] No unauthorized autorun modifications detected.")

    elif args.command == "take-baseline":
        inspector = PersistenceInspector()
        result = inspector.take_baseline()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"[OK] Baseline snapshot captured successfully.")
            print(f"  Recorded {result['baseline_count']} autorun entries to {result['file']}")


if __name__ == "__main__":
    main()
