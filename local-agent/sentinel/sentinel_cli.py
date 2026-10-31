"""
================================================================================
Voila Sentinel CLI - Endpoint Telemetry & Threat Defense Interface
================================================================================
Commands:
  status             - Complete posture sweep (Ports + Processes + Persistence)
  audit-ports        - Audits listening TCP/UDP sockets for wildcard/dev-server leakage
  scan-processes     - Inspects active process tree for obfuscated & suspicious commands
  audit-persistence  - Audits Registry Run keys and Startup folder against baseline
  take-baseline      - Captures current autoruns as trusted baseline
  triage-file        - Runs static PE / Script analysis on a specific file (No execution)
  scan-downloads     - Audits user Downloads directory for suspicious binaries
  quarantine-file    - Safely scrambles and isolates an untrusted file into the vault
  list-vault         - Displays all quarantined items and audit manifest
  restore-file       - Reversibly restores a false-positive file back to disk
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
from sentinel.pe_triage import StaticPETriage
from sentinel.quarantine_vault import quarantine_vault
from sentinel.download_sentinel import download_sentinel


def print_banner():
    print("""
+-------------------------------------------------------------+
|          VOILA SENTINEL - PERSONAL CYBER DEFENSE            |
|              Endpoint Telemetry & Threat Core               |
+-------------------------------------------------------------+
    """)


def main():
    parser = argparse.ArgumentParser(description="Voila Sentinel Security CLI")
    parser.add_argument("command", choices=[
        "status", "audit-ports", "scan-processes", "audit-persistence", "take-baseline",
        "triage-file", "scan-downloads", "quarantine-file", "list-vault", "restore-file"
    ], help="Command to execute")
    parser.add_argument("--target", "-t", type=str, help="Target file path for triage or quarantine")
    parser.add_argument("--id", type=str, help="Vault ID for restoration")
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

    elif args.command == "triage-file":
        if not args.target:
            print("Error: --target <path> required for triage-file")
            sys.exit(1)
        result = StaticPETriage.triage_file(args.target)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"File: {result.get('filename')} ({result.get('file_size', 0)} bytes)")
            print(f"Verdict: {result.get('verdict')} | Threat Score: {result.get('threat_score')}/100")
            print(f"SHA-256: {result.get('sha256')}")
            if result.get("indicators"):
                print("\nIndicators:")
                for ind in result["indicators"]:
                    print(f"  - {ind}")

    elif args.command == "scan-downloads":
        result = download_sentinel.scan_downloads()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Directory: {result['downloads_dir']}")
            print(f"Total Executables/Scripts: {result['total_executable_files']} | Threats Found: {result['threats_count']}")
            if result["threats"]:
                print("\n[!] Threats Identified in Downloads:")
                for t in result["threats"]:
                    print(f"  - [{t['verdict']}] {t['filename']} (Threat Score: {t['threat_score']}): {', '.join(t.get('indicators', []))}")
            else:
                print("\n[OK] No malicious or suspicious files found in Downloads.")

    elif args.command == "quarantine-file":
        if not args.target:
            print("Error: --target <path> required for quarantine-file")
            sys.exit(1)
        triage = StaticPETriage.triage_file(args.target)
        result = quarantine_vault.quarantine_file(
            filepath=args.target,
            reasons=triage.get("indicators", ["User Initiated Quarantine"]),
            threat_score=triage.get("threat_score", 100.0)
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            if result.get("status") == "SUCCESS":
                print(f"[OK] File successfully scrambled and quarantined.")
                print(f"  Vault ID: {result['vault_id']}")
                print(f"  Original Path: {result['original_path']}")
                print(f"  SHA-256: {result['sha256']}")
            else:
                print(f"[ERROR] Quarantine failed: {result.get('message')}")

    elif args.command == "list-vault":
        items = quarantine_vault.list_vault()
        if args.json:
            print(json.dumps(items, indent=2))
        else:
            print_banner()
            print(f"Quarantined Items Count: {len(items)}")
            for item in items:
                print(f"  - ID: {item['vault_id']} | Status: {item['status']} | File: {item['original_filename']}")
                print(f"    Path: {item['original_path']}")
                print(f"    Quarantined At: {item['quarantined_at']} | Threat Score: {item.get('threat_score')}")

    elif args.command == "restore-file":
        if not args.id:
            print("Error: --id <vault_id> required for restore-file")
            sys.exit(1)
        result = quarantine_vault.restore_file(args.id)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            if result.get("status") == "SUCCESS":
                print(f"[OK] File successfully descrambled and restored.")
                print(f"  Restored Path: {result['restored_path']}")
                print(f"  SHA-256 Verified: {result['sha256']}")
            else:
                print(f"[ERROR] Restoration failed: {result.get('message')}")


if __name__ == "__main__":
    main()
