"""
================================================================================
Voila Sentinel CLI - Endpoint Telemetry & Threat Defense Interface
================================================================================
Commands:
  status             - Complete posture sweep (Ports + Processes + Persistence + LAN + Secrets)
  audit-ports        - Audits listening TCP/UDP sockets for wildcard/dev-server leakage
  scan-processes     - Inspects active process tree for obfuscated & suspicious commands
  audit-persistence  - Audits Registry Run keys and Startup folder against baseline
  take-baseline      - Captures current autoruns as trusted baseline
  triage-file        - Runs static PE / Script analysis on a specific file (No execution)
  scan-downloads     - Audits user Downloads directory for suspicious binaries
  quarantine-file    - Safely scrambles and isolates an untrusted file into the vault
  list-vault         - Displays all quarantined items and audit manifest
  restore-file       - Reversibly restores a false-positive file back to disk
  scan-lan           - Passively discovers active LAN devices and monitors router ARP
  audit-gateway      - Verifies gateway MAC address against cache poisoning (Anti-MITM)
  take-network-base  - Snapshots local network topology baseline
  scan-secrets       - Recursively audits code & configs for cloud tokens & API keys
  check-breach       - Evaluates credential exposure via k-Anonymity (zero plaintext leak)
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
from sentinel.lan_guardian import lan_guardian
from sentinel.secret_scanner import secret_scanner
from sentinel.identity_radar import identity_radar


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
        "triage-file", "scan-downloads", "quarantine-file", "list-vault", "restore-file",
        "scan-lan", "audit-gateway", "take-network-baseline",
        "scan-secrets", "check-breach"
    ], help="Command to execute")
    parser.add_argument("--target", "-t", type=str, help="Target file path for triage or quarantine")
    parser.add_argument("--dir", "-d", type=str, help="Target directory for secret scanning")
    parser.add_argument("--secret", "-s", type=str, help="Credential or secret string to test against breach radar")
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

    elif args.command == "scan-lan":
        result = lan_guardian.scan_local_devices()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Risk Level: {result['risk_level']} | Active Adapter: {result.get('active_adapter')} ({result.get('local_ip')})")
            print(f"Subnet Devices Discovered: {result['total_subnet_devices']} | Scan Duration: {result['scan_duration_ms']}ms")
            gw = result.get("gateway", {})
            print(f"\nGateway Router: {gw.get('gateway_ip')} [{gw.get('gateway_mac')}] - {gw.get('gateway_vendor')}")
            print(f"Gateway Status: {gw.get('status')}")
            if result["devices"]:
                print("\nActive Subnet Assets:")
                for d in result["devices"]:
                    flag = " [NEW]" if d.get("is_new_to_network") else ""
                    print(f"  - {d['ip']:<16} {d['mac']:<18} ({d['type']}) : {d['vendor']}{flag}")

    elif args.command == "audit-gateway":
        result = lan_guardian.audit_gateway()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Gateway IP: {result.get('gateway_ip')} | Gateway MAC: {result.get('gateway_mac')}")
            print(f"Hardware Vendor: {result.get('gateway_vendor')}")
            print(f"Status: {result.get('status')}")
            if result.get("is_spoofed"):
                print("\n[CRITICAL ALERT] Gateway ARP spoofing detected!")
                for r in result.get("reasons", []):
                    print(f"  - {r}")
            else:
                print("\n[OK] Gateway ARP integrity verified. No cache poisoning detected.")

    elif args.command == "take-network-baseline":
        result = lan_guardian.take_network_baseline()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"[OK] Network baseline snapshot captured successfully.")
            print(f"  Gateway IP: {result.get('gateway_ip')} [{result.get('gateway_mac')}]")
            print(f"  Recorded {result.get('devices_count')} active subnet devices to {result.get('baseline_file')}")

    elif args.command == "scan-secrets":
        target_dir = args.dir if args.dir else os.getcwd()
        result = secret_scanner.scan_directory(target_dir)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print(f"Risk Level: {result.get('risk_level')} | Scanned: {result.get('files_scanned')} files")
            print(f"Directory: {result.get('scanned_directory')}")
            findings = result.get("findings", [])
            print(f"Total Secrets Found: {len(findings)}")
            if findings:
                print("\n[!] Exposed Credentials Detected:")
                for f in findings:
                    print(f"  - [{f['severity']}] {f['type']} at line {f['line']}")
                    print(f"    File: {f['source']}")
                    print(f"    Token Mask: {f['masked']}")
            else:
                print("\n[OK] Zero exposed secrets, API keys, or private keys detected.")

    elif args.command == "check-breach":
        if not args.secret:
            print("Error: --secret <string> required for check-breach")
            sys.exit(1)
        result = identity_radar.check_pwned_secret(args.secret)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_banner()
            print("Privacy Status: k-Anonymity Preserved (Transmitted SHA-1 prefix only)")
            print(f"SHA-1 Prefix Transmitted: {result.get('sha1_prefix')}*****")
            print(f"Verdict: {result.get('risk_verdict')}")
            if result.get("is_breached"):
                print(f"\n[CRITICAL WARNING] This credential was found in {result.get('breach_count'):,} public breach records!")
                print("Action Required: Rotate this credential immediately. It is known to adversary dictionaries.")
            else:
                print(f"\n[OK] Credential does not appear in known public data breaches.")


if __name__ == "__main__":
    main()
