"""
================================================================================
Voila Sentinel - Static Portable Executable (PE) & Script Triage Engine
================================================================================
Capabilities:
1. 100% In-Code & Pure Python (struct-based PE Header parsing).
2. Shannon Entropy Analysis: Detects packed, obfuscated, or encrypted sections (>7.2).
3. Packer Signature Detection (UPX, ASPack, MPRESS, FSG, Themida).
4. Dangerous API Import Scanning (Injection, Downloader, Anti-Debugging, Keylogging).
5. Windows Authenticode Digital Signature Verification.
6. Script Triage (.vbs, .ps1, .bat, .js, .hta) for encoded payloads and living-off-the-land commands.
7. Strictly STATIC: Never executes or dynamically loads untrusted binaries.
================================================================================
"""

import os
import sys
import math
import struct
import hashlib
import subprocess
from typing import Dict, List, Any, Optional, Tuple


def calculate_entropy(data: bytes) -> float:
    """Calculates Shannon entropy in bits per byte (0.0 to 8.0). Values > 7.2 indicate encryption/packing."""
    if not data:
        return 0.0
    freq = [0] * 256
    for b in data:
        freq[b] += 1
    total = len(data)
    entropy = 0.0
    for count in freq:
        if count > 0:
            p = float(count) / total
            entropy -= p * math.log(p, 2)
    return entropy


class StaticPETriage:
    """Static PE header analyzer and threat evaluator."""

    DANGEROUS_IMPORTS = {
        # Process Injection / Memory Tampering
        "virtualalloc": "Memory Allocation (Potential Shellcode Injection)",
        "virtualallocex": "Remote Process Memory Allocation (Process Injection)",
        "writeprocessmemory": "Remote Process Memory Write (Process Injection)",
        "createremotethread": "Remote Thread Creation (Process Injection)",
        "queueuserapc": "Early Bird / APC Queue Injection",
        "setthreadcontext": "Thread Hijacking",
        "ntunmapviewofsection": "Process Hollowing (RunPE)",
        # Ingress / Downloader
        "urldownloadtofilea": "Trojan Ingress Downloader",
        "urldownloadtofilew": "Trojan Ingress Downloader",
        "internetopenurla": "HTTP Ingress Connection",
        "internetopenurlw": "HTTP Ingress Connection",
        "httpsendrequesta": "C2 HTTP Request",
        # Anti-Debugging / Evasion
        "isdebuggerpresent": "Anti-Debugging Check",
        "checkremotedebuggerpresent": "Anti-Debugging Check",
        # Keylogging / Snooping
        "getasynckeystate": "Keystroke Interception",
        "setwindowshookexa": "Global Windows Hooking (Keylogger / Spyware)",
        "setwindowshookexw": "Global Windows Hooking (Keylogger / Spyware)"
    }

    KNOWN_PACKERS = ("upx", "aspack", "mpress", "fsg", "themida", "vmp", "pec")

    @classmethod
    def check_authenticode(cls, filepath: str) -> Tuple[bool, str]:
        """Verifies if the binary possesses a valid digital signature using Windows Authenticode."""
        try:
            # Query PowerShell Get-AuthenticodeSignature safely
            cmd = [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                f"(Get-AuthenticodeSignature -FilePath '{filepath}').Status.ToString()"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            status_str = res.stdout.strip()
            if status_str == "Valid":
                return True, "Valid Authenticode Signature"
            elif status_str in ("NotSigned", "UnknownError", ""):
                return False, "Unsigned Binary"
            else:
                return False, f"Signature Status: {status_str}"
        except Exception:
            return False, "Authenticode Check Inconclusive"

    @classmethod
    def triage_pe_binary(cls, filepath: str) -> Dict[str, Any]:
        """Performs comprehensive static triage on a Windows PE executable (.exe/.dll)."""
        if not os.path.exists(filepath):
            return {"error": f"File not found: {filepath}", "threat_score": 0.0}

        file_size = os.path.getsize(filepath)
        if file_size > 80 * 1024 * 1024:
            # Skip massive files for static analysis
            return {"status": "SKIPPED_OVERSIZE", "threat_score": 0.0, "file_size": file_size}

        with open(filepath, "rb") as f:
            data = f.read()

        file_sha256 = hashlib.sha256(data).hexdigest()

        if len(data) < 64 or data[:2] != b"MZ":
            return {"is_pe": False, "threat_score": 0.0, "reason": "Not an MZ binary"}

        e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
        if e_lfanew + 24 > len(data):
            return {"is_pe": False, "threat_score": 0.0, "reason": "Corrupt DOS Header"}

        if data[e_lfanew:e_lfanew + 4] != b"PE\x00\x00":
            return {"is_pe": False, "threat_score": 0.0, "reason": "Invalid PE Signature"}

        file_header_offset = e_lfanew + 4
        machine, num_sections, time_date, _, _, opt_hdr_size, characteristics = struct.unpack_from(
            "<HHIIIHH", data, file_header_offset
        )
        is_64bit = (machine == 0x8664)
        arch = "x64" if is_64bit else "x86" if machine == 0x014c else f"0x{machine:04x}"

        opt_header_offset = file_header_offset + 20
        sections_offset = opt_header_offset + opt_hdr_size

        sections = []
        indicators = []
        threat_score = 0.0

        has_high_entropy_section = False
        has_packer_section = False

        for i in range(num_sections):
            sec_hdr = sections_offset + (i * 40)
            if sec_hdr + 40 > len(data):
                break
            name = data[sec_hdr:sec_hdr + 8].rstrip(b"\x00").decode("latin-1", errors="ignore")
            vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<IIII", data, sec_hdr + 8)

            sec_data = data[raw_ptr:raw_ptr + raw_size] if raw_ptr + raw_size <= len(data) else b""
            ent = calculate_entropy(sec_data) if sec_data else 0.0

            name_lower = name.lower()
            if any(p in name_lower for p in cls.KNOWN_PACKERS):
                has_packer_section = True
                indicators.append(f"Known Packer Section Detected: '{name}'")
                threat_score += 35.0

            if ent > 7.2 and raw_size > 4096:
                has_high_entropy_section = True
                indicators.append(f"High-Entropy Section Detected: '{name}' (Entropy: {ent:.2f}/8.0 - Likely Packed/Encrypted)")
                threat_score += 25.0

            sections.append({
                "name": name,
                "raw_size": raw_size,
                "entropy": round(ent, 2)
            })

        overall_entropy = calculate_entropy(data)
        if overall_entropy > 7.3:
            threat_score += 15.0
            indicators.append(f"Elevated Overall Binary Entropy ({overall_entropy:.2f}/8.0)")

        # Scan for dangerous string/import signatures
        data_lower = data.lower()
        matched_imports = []
        for fn, desc in cls.DANGEROUS_IMPORTS.items():
            fn_bytes = fn.encode("ascii")
            if fn_bytes in data_lower:
                matched_imports.append(f"{fn} ({desc})")

        if matched_imports:
            threat_score += min(40.0, len(matched_imports) * 10.0)
            indicators.append(f"Detected {len(matched_imports)} Offensive API Import(s): {', '.join(matched_imports[:4])}")

        # Authenticode Signature Verification
        is_signed, sig_details = cls.check_authenticode(filepath)
        if is_signed:
            # Valid signature from vendor significantly reduces risk
            threat_score = max(0.0, threat_score - 40.0)
            indicators.append(f"Digitally Signed: {sig_details}")
        else:
            threat_score += 15.0
            indicators.append("Unsigned Binary (No Valid Authenticode Certificate)")

        threat_score = max(0.0, min(100.0, threat_score))

        if threat_score >= 70.0:
            verdict = "HIGH_RISK"
        elif threat_score >= 40.0:
            verdict = "SUSPICIOUS"
        else:
            verdict = "CLEAN"

        return {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "file_size": file_size,
            "sha256": file_sha256,
            "is_pe": True,
            "arch": arch,
            "sections_count": num_sections,
            "overall_entropy": round(overall_entropy, 2),
            "is_digitally_signed": is_signed,
            "signature_status": sig_details,
            "threat_score": round(threat_score, 1),
            "verdict": verdict,
            "indicators": indicators,
            "sections": sections
        }

    @classmethod
    def triage_script(cls, filepath: str) -> Dict[str, Any]:
        """Performs static analysis on script files (.vbs, .ps1, .bat, .cmd, .js, .hta)."""
        if not os.path.exists(filepath):
            return {"error": f"File not found: {filepath}", "threat_score": 0.0}

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            return {"error": f"Failed to read script: {e}", "threat_score": 0.0}

        content_lower = content.lower()
        threat_score = 0.0
        indicators = []

        if "-enc" in content_lower or "-encodedcommand" in content_lower:
            threat_score += 40.0
            indicators.append("Base64 Encoded PowerShell Command (-enc)")

        if "-w hidden" in content_lower or "-windowstyle hidden" in content_lower:
            threat_score += 25.0
            indicators.append("Hidden Execution Window (-w hidden)")

        if any(term in content_lower for term in ("downloadstring", "invoke-expression", "iex(", "iwr http", "curl http")):
            threat_score += 35.0
            indicators.append("In-Memory Remote Download & Execution (IEX)")

        if "wscript.shell" in content_lower and any(ext in content_lower for ext in (".vbs", ".bat", ".cmd", ".ps1")):
            threat_score += 20.0
            indicators.append("WScript.Shell Dropper / Launcher")

        ent = calculate_entropy(content.encode("utf-8", errors="ignore"))
        if ent > 5.5 and len(content) > 200:
            threat_score += 20.0
            indicators.append(f"Elevated Script Shannon Entropy ({ent:.2f})")

        threat_score = max(0.0, min(100.0, threat_score))

        if threat_score >= 65.0:
            verdict = "HIGH_RISK"
        elif threat_score >= 35.0:
            verdict = "SUSPICIOUS"
        else:
            verdict = "CLEAN"

        return {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "file_size": os.path.getsize(filepath),
            "sha256": hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest(),
            "is_pe": False,
            "is_script": True,
            "script_entropy": round(ent, 2),
            "threat_score": round(threat_score, 1),
            "verdict": verdict,
            "indicators": indicators
        }

    @classmethod
    def triage_file(cls, filepath: str) -> Dict[str, Any]:
        """Auto-detects file type and runs appropriate static triage."""
        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".exe", ".dll", ".sys", ".scr"):
            return cls.triage_pe_binary(filepath)
        elif ext in (".vbs", ".ps1", ".bat", ".cmd", ".js", ".hta"):
            return cls.triage_script(filepath)
        else:
            # Check for MZ header even if extension is disguised
            try:
                with open(filepath, "rb") as f:
                    magic = f.read(2)
                if magic == b"MZ":
                    return cls.triage_pe_binary(filepath)
            except Exception:
                pass
            return {
                "filepath": filepath,
                "filename": os.path.basename(filepath),
                "is_pe": False,
                "is_script": False,
                "threat_score": 0.0,
                "verdict": "CLEAN",
                "indicators": ["Non-executable document or media file."]
            }
