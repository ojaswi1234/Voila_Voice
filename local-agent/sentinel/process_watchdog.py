"""
================================================================================
Voila Sentinel - Process Watchdog & Command-Line Behavioral Telemetry
================================================================================
Monitors Windows processes for suspicious activity:
1. Obfuscated Base64 commands (-enc, -encodedcommand).
2. Hidden execution flags (-w hidden, -windowstyle hidden).
3. In-memory downloads & living-off-the-land techniques (LOLBins).
4. Command line Shannon entropy calculation (>5.0 indicates packing/obfuscation).
5. Parent-child anomalies (Office/PDF apps spawning shells).
================================================================================
"""

import os
import math
import psutil
from typing import Dict, List, Any


def calculate_shannon_entropy(text: str) -> float:
    """Calculates Shannon entropy of a string (bits per char). High entropy indicates obfuscation."""
    if not text:
        return 0.0
    probabilities = [float(text.count(c)) / len(text) for c in set(text)]
    return -sum(p * math.log(p) / math.log(2.0) for p in probabilities)


class ProcessWatchdog:
    """Non-intrusive process telemetry and anomaly detector."""

    SUSPICIOUS_SHELLS = ("powershell.exe", "cmd.exe", "wscript.exe", "cscript.exe", "mshta.exe", "rundll32.exe")
    OFFICE_PARENTS = ("winword.exe", "excel.exe", "powerpnt.exe", "acrord32.exe", "outlook.exe")

    # Common Living-off-the-land binaries
    LOLBINS = ("certutil.exe", "bitsadmin.exe", "mshta.exe", "regsvr32.exe", "wmic.exe")

    @classmethod
    def evaluate_command_line(cls, cmd: str) -> tuple:
        """Evaluates a raw command line string for malicious, obfuscated, or LOLBin patterns.
        Returns: (is_anomaly: bool, severity: str, reasons: List[str])
        """
        if not cmd:
            return False, "CLEAN", []
        cmd_lower = cmd.lower()
        reasons = []
        severity = "CLEAN"

        # Check for encoded commands
        if "-enc" in cmd_lower or "-encodedcommand" in cmd_lower:
            reasons.append("Base64 Encoded Command Line (-enc)")
            severity = "HIGH"

        # Check for hidden window style
        if "-w hidden" in cmd_lower or "-windowstyle hidden" in cmd_lower:
            reasons.append("Hidden Execution Window (-w hidden)")
            if severity != "HIGH":
                severity = "MEDIUM"

        # Check for in-memory download & execution
        if any(term in cmd_lower for term in ("downloadstring", "invoke-expression", "iex(", "iwr http", "curl http")):
            reasons.append("In-Memory Remote Download & Execution (IEX)")
            severity = "HIGH"

        # Check Shannon Entropy on long command lines
        if len(cmd) > 120:
            entropy = calculate_shannon_entropy(cmd)
            if entropy > 5.1:
                reasons.append(f"High Command-Line Entropy ({entropy:.2f})")
                if severity != "HIGH":
                    severity = "MEDIUM"

        # Check LOLBins abuse
        if any(bin_name in cmd_lower for bin_name in ("certutil", "bitsadmin", "mshta", "regsvr32")):
            if "certutil" in cmd_lower and ("-urlcache" in cmd_lower or "-split" in cmd_lower):
                reasons.append("Certutil Ingress Tool Transfer (-urlcache)")
                severity = "HIGH"
            elif "bitsadmin" in cmd_lower and "/transfer" in cmd_lower:
                reasons.append("Bitsadmin Ingress Tool Transfer (/transfer)")
                severity = "HIGH"
            elif "mshta" in cmd_lower and "http" in cmd_lower:
                reasons.append("MSHTA Remote Script Execution")
                severity = "HIGH"
            elif "regsvr32" in cmd_lower and ("/s" in cmd_lower and "/u" in cmd_lower and "/i:" in cmd_lower):
                reasons.append("Regsvr32 Squiblydoo Bypass (/s /u /i:)")
                severity = "HIGH"

        is_anom = (len(reasons) > 0)
        return is_anom, severity, reasons

    @classmethod
    def scan(cls) -> Dict[str, Any]:
        """Scans current process table and flags suspicious behaviors."""
        total_checked = 0
        anomalies = []

        my_pid = os.getpid()

        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
            total_checked += 1
            try:
                pid = proc.info['pid']
                if pid == my_pid:
                    continue  # Ignore self

                pname = (proc.info['name'] or '').lower()
                cmd_list = proc.info['cmdline'] or []
                cmd = " ".join(cmd_list)
                cmd_lower = cmd.lower()
                ppid = proc.info.get('ppid')

                # Check 1: Shells and script interpreters
                if pname in cls.SUSPICIOUS_SHELLS:
                    reasons = []
                    severity = "LOW"

                    # Check for encoded commands
                    if "-enc" in cmd_lower or "-encodedcommand" in cmd_lower:
                        reasons.append("Base64 Encoded Command Line (-enc)")
                        severity = "HIGH"

                    # Check for hidden window style
                    if "-w hidden" in cmd_lower or "-windowstyle hidden" in cmd_lower:
                        reasons.append("Hidden Execution Window (-w hidden)")
                        if severity != "HIGH":
                            severity = "MEDIUM"

                    # Check for in-memory download & execution
                    if any(term in cmd_lower for term in ("downloadstring", "invoke-expression", "iex(", "iwr http", "curl http")):
                        reasons.append("In-Memory Remote Download & Execution (IEX)")
                        severity = "HIGH"

                    # Check Shannon Entropy on long command lines
                    if len(cmd) > 120:
                        entropy = calculate_shannon_entropy(cmd)
                        if entropy > 5.1:
                            reasons.append(f"High Command-Line Entropy ({entropy:.2f})")
                            if severity != "HIGH":
                                severity = "MEDIUM"

                    # Check Parent-Child Anomaly
                    if ppid:
                        try:
                            parent = psutil.Process(ppid)
                            parent_name = (parent.name() or '').lower()
                            if parent_name in cls.OFFICE_PARENTS:
                                reasons.append(f"Suspicious Parent Process ({parent_name} spawned {pname})")
                                severity = "CRITICAL"
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    if reasons:
                        anomalies.append({
                            "pid": pid,
                            "process_name": pname,
                            "severity": severity,
                            "reasons": reasons,
                            "cmdline": cmd[:250] + ("..." if len(cmd) > 250 else "")
                        })

                # Check 2: LOLBins abuse
                elif pname in cls.LOLBINS:
                    reasons = []
                    if "certutil" in pname and ("-urlcache" in cmd_lower or "-split" in cmd_lower):
                        reasons.append("Certutil Ingress Tool Transfer (-urlcache)")
                    elif "bitsadmin" in pname and "/transfer" in cmd_lower:
                        reasons.append("Bitsadmin Ingress Tool Transfer (/transfer)")
                    elif "mshta" in pname and "http" in cmd_lower:
                        reasons.append("MSHTA Remote Script Execution")
                    elif "regsvr32" in pname and ("/s" in cmd_lower and "/u" in cmd_lower and "/i:" in cmd_lower):
                        reasons.append("Regsvr32 Squiblydoo Bypass (/s /u /i:)")

                    if reasons:
                        anomalies.append({
                            "pid": pid,
                            "process_name": pname,
                            "severity": "HIGH",
                            "reasons": reasons,
                            "cmdline": cmd[:250] + ("..." if len(cmd) > 250 else "")
                        })

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        risk_level = "HEALTHY"
        if any(a["severity"] == "CRITICAL" for a in anomalies):
            risk_level = "CRITICAL"
        elif any(a["severity"] == "HIGH" for a in anomalies):
            risk_level = "WARNING"
        elif anomalies:
            risk_level = "INFO"

        return {
            "risk_level": risk_level,
            "total_processes_checked": total_checked,
            "total_anomalies": len(anomalies),
            "anomalies": anomalies
        }
