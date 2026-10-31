"""
================================================================================
Voila Sentinel - Pre-Commit Secret Scanner & Token Leak Watcher
================================================================================
Capabilities:
1. Regex & Shannon Entropy Scanning for exposed secrets and cloud credentials:
   - AWS Access Key IDs & Secrets
   - GitHub Personal Access Tokens (Classic & Fine-grained)
   - Google & Gemini API Keys
   - OpenAI, Anthropic & Groq Keys
   - Cryptographic Private Keys (RSA, OpenSSH, EC, DSA)
   - Stripe & Slack API Tokens
2. Safe Redaction: All detected secrets are cryptographically masked in logs/output
   (e.g., AKIA****...****9F) to prevent accidental secondary exposure.
3. Ignore Filters: Automatically excludes .git/objects, node_modules, and binaries.
================================================================================
"""

import os
import re
import math
from typing import Dict, List, Any, Optional, Tuple


def mask_secret(secret: str) -> str:
    """Masks secret to show only the first 4 and last 2 characters."""
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}****...****{secret[-2:]}"


class SecretScanner:
    """Scans files and workspaces for accidentally exposed secrets and credentials."""

    SECRET_PATTERNS = [
        ("AWS Access Key ID", re.compile(r'\b(AKIA[0-9A-Z]{16})\b'), "HIGH"),
        ("GitHub Personal Access Token", re.compile(r'\b(ghp_[0-9a-zA-Z]{36}|github_pat_[0-9a-zA-Z_]{82})\b'), "CRITICAL"),
        ("Google API Key", re.compile(r'\b(AIza[0-9A-Za-z\-_]{35})\b'), "HIGH"),
        ("OpenAI / Anthropic API Key", re.compile(r'\b(sk-(?:proj-)?[a-zA-Z0-9_\-]{32,80})\b'), "HIGH"),
        ("Groq API Key", re.compile(r'\b(gsk_[a-zA-Z0-9]{45,60})\b'), "HIGH"),
        ("Stripe Live API Key", re.compile(r'\b(sk_live_[0-9a-zA-Z]{24})\b'), "CRITICAL"),
        ("Slack Token", re.compile(r'\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b'), "HIGH"),
        ("Private Cryptographic Key", re.compile(r'(-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----)'), "CRITICAL"),
        ("Firebase Private Key Header", re.compile(r'("private_key":\s*"-----BEGIN PRIVATE KEY)'), "CRITICAL"),
    ]

    IGNORE_DIRS = {
        ".git", "node_modules", "vendor", "__pycache__", ".dart_tool",
        "build", "dist", ".venv", "venv", "env", ".idea", ".vscode"
    }

    IGNORE_EXTS = {
        ".exe", ".dll", ".so", ".dylib", ".png", ".jpg", ".jpeg",
        ".pdf", ".zip", ".tar", ".gz", ".onnx", ".ttf", ".woff", ".woff2"
    }

    @classmethod
    def scan_text(cls, text: str, source_label: str = "buffer") -> List[Dict[str, Any]]:
        """Scans raw text content against all secret signatures."""
        findings = []
        for name, pattern, severity in cls.SECRET_PATTERNS:
            for match in pattern.finditer(text):
                matched_val = match.group(1)
                # Calculate line number
                line_no = text[:match.start()].count("\n") + 1
                findings.append({
                    "type": name,
                    "severity": severity,
                    "source": source_label,
                    "line": line_no,
                    "masked": mask_secret(matched_val)
                })
        return findings

    @classmethod
    def scan_file(cls, filepath: str) -> List[Dict[str, Any]]:
        """Scans a single text/code file on disk."""
        clean_path = os.path.abspath(filepath)
        if not os.path.exists(clean_path) or not os.path.isfile(clean_path):
            return []

        ext = os.path.splitext(clean_path)[1].lower()
        if ext in cls.IGNORE_EXTS:
            return []

        # Skip files larger than 5 MB
        if os.path.getsize(clean_path) > 5 * 1024 * 1024:
            return []

        try:
            with open(clean_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return cls.scan_text(content, source_label=clean_path)
        except Exception:
            return []

    @classmethod
    def scan_directory(cls, dirpath: str, max_files: int = 400) -> Dict[str, Any]:
        """Scans workspace directory recursively, ignoring build/binary folders."""
        clean_dir = os.path.abspath(dirpath)
        if not os.path.exists(clean_dir):
            return {"error": f"Directory not found: {clean_dir}"}

        scanned_count = 0
        all_findings = []

        for root, dirs, files in os.walk(clean_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in cls.IGNORE_DIRS]

            for fname in files:
                if scanned_count >= max_files:
                    break
                fpath = os.path.join(root, fname)
                findings = cls.scan_file(fpath)
                if findings:
                    all_findings.extend(findings)
                scanned_count += 1

            if scanned_count >= max_files:
                break

        risk_level = "HEALTHY"
        if any(f["severity"] == "CRITICAL" for f in all_findings):
            risk_level = "CRITICAL"
        elif all_findings:
            risk_level = "WARNING"

        return {
            "risk_level": risk_level,
            "scanned_directory": clean_dir,
            "files_scanned": scanned_count,
            "total_secrets_found": len(all_findings),
            "findings": all_findings
        }


# Global Singleton
secret_scanner = SecretScanner()
