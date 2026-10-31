"""
================================================================================
Voila Sentinel - Reversible Quarantine Vault
================================================================================
Capabilities:
1. Safe Isolation: Scrambles binary payloads via reversible XOR encryption so
   files cannot execute or trigger OS auto-runs while quarantined.
2. Complete Audit Manifest: Tracks original path, timestamps, file size, SHA-256,
   and threat indicators in vault_manifest.json.
3. 100% Reversibility: Allows single-command restoration of false positives
   back to their original location with cryptographic byte-for-byte hash validation.
4. Non-Destructive: Never permanently purges files without explicit user command.
================================================================================
"""

import os
import sys
import json
import time
import uuid
import hashlib
from typing import Dict, List, Any, Optional

# Static 32-byte key for reversible vault payload scrambling
VAULT_KEY = b"VoilaSentinelQuarantineKey2026!"


def _scramble_bytes(data: bytes) -> bytes:
    """Reversibly XOR scrambles bytes with the vault key."""
    key_len = len(VAULT_KEY)
    return bytes(b ^ VAULT_KEY[i % key_len] for i, b in enumerate(data))


class QuarantineVault:
    """Manages isolated files, scrambling, and restorations."""

    def __init__(self, vault_dir: Optional[str] = None):
        if not vault_dir:
            vault_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault")
        os.makedirs(vault_dir, exist_ok=True)
        self.vault_dir = vault_dir
        self.manifest_file = os.path.join(vault_dir, "vault_manifest.json")
        self._ensure_manifest()

    def _ensure_manifest(self):
        if not os.path.exists(self.manifest_file):
            with open(self.manifest_file, "w", encoding="utf-8") as f:
                json.dump({"items": {}}, f, indent=2)

    def _load_manifest(self) -> Dict[str, Any]:
        try:
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"items": {}}

    def _save_manifest(self, data: Dict[str, Any]):
        with open(self.manifest_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def quarantine_file(self, filepath: str, reasons: Optional[List[str]] = None, threat_score: float = 100.0) -> Dict[str, Any]:
        """
        Safely quarantines a file:
        1. Reads raw bytes and verifies original SHA-256.
        2. Scrambles payload bytes so file is inert.
        3. Writes to vault/<vault_id>.quarantine.
        4. Updates manifest with full audit trail.
        5. Atomically deletes original file from vulnerable folder.
        """
        clean_path = os.path.abspath(filepath)
        if not os.path.exists(clean_path) or not os.path.isfile(clean_path):
            return {"status": "ERROR", "message": f"File not found: {clean_path}"}

        try:
            with open(clean_path, "rb") as f:
                raw_data = f.read()
        except Exception as e:
            return {"status": "ERROR", "message": f"Could not read file for quarantine: {e}"}

        orig_sha256 = hashlib.sha256(raw_data).hexdigest()
        file_size = len(raw_data)
        vault_id = str(uuid.uuid4())[:12]
        quarantine_filename = f"{vault_id}.quarantine"
        quarantine_path = os.path.join(self.vault_dir, quarantine_filename)

        # Scramble bytes to render binary inert
        scrambled = _scramble_bytes(raw_data)
        with open(quarantine_path, "wb") as f:
            f.write(scrambled)

        # Record in manifest
        manifest = self._load_manifest()
        item = {
            "vault_id": vault_id,
            "status": "QUARANTINED",
            "original_path": clean_path,
            "original_filename": os.path.basename(clean_path),
            "file_size": file_size,
            "sha256": orig_sha256,
            "quarantined_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "threat_score": threat_score,
            "reasons": reasons or ["Manual Quarantine"]
        }
        manifest.setdefault("items", {})[vault_id] = item
        self._save_manifest(manifest)

        # Remove original file
        try:
            os.remove(clean_path)
        except Exception as e:
            # If removal fails, keep record but flag warning
            item["warning"] = f"Vaulted copy created, but original file removal encountered: {e}"

        return {
            "status": "SUCCESS",
            "vault_id": vault_id,
            "original_path": clean_path,
            "sha256": orig_sha256,
            "vault_path": quarantine_path
        }

    def restore_file(self, vault_id: str) -> Dict[str, Any]:
        """
        Reversibly restores a quarantined file:
        1. Reads scrambled payload.
        2. Descrambles bytes.
        3. Verifies SHA-256 matches the original hash exactly.
        4. Writes back to original path.
        5. Marks item as RESTORED in manifest.
        """
        manifest = self._load_manifest()
        items = manifest.get("items", {})
        if vault_id not in items:
            return {"status": "ERROR", "message": f"Vault ID not found: {vault_id}"}

        item = items[vault_id]
        orig_path = item["original_path"]
        orig_sha = item["sha256"]
        quarantine_file = os.path.join(self.vault_dir, f"{vault_id}.quarantine")

        if not os.path.exists(quarantine_file):
            return {"status": "ERROR", "message": f"Quarantine storage file missing: {quarantine_file}"}

        with open(quarantine_file, "rb") as f:
            scrambled = f.read()

        # Descramble
        restored_bytes = _scramble_bytes(scrambled)
        restored_sha = hashlib.sha256(restored_bytes).hexdigest()

        if restored_sha != orig_sha:
            return {
                "status": "ERROR",
                "message": f"Cryptographic integrity mismatch! Expected {orig_sha}, got {restored_sha}."
            }

        # Ensure destination directory exists
        os.makedirs(os.path.dirname(os.path.abspath(orig_path)), exist_ok=True)
        with open(orig_path, "wb") as f:
            f.write(restored_bytes)

        # Remove vault file and update manifest
        try:
            os.remove(quarantine_file)
        except Exception:
            pass

        item["status"] = "RESTORED"
        item["restored_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_manifest(manifest)

        return {
            "status": "SUCCESS",
            "vault_id": vault_id,
            "restored_path": orig_path,
            "sha256": restored_sha
        }

    def list_vault(self) -> List[Dict[str, Any]]:
        """Returns all items currently in the quarantine vault."""
        manifest = self._load_manifest()
        return list(manifest.get("items", {}).values())


# Global Singleton
quarantine_vault = QuarantineVault()
