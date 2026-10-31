"""
================================================================================
Voila Sentinel - Baseline Cryptographic Integrity & Anti-Tamper Sealing
================================================================================
Capabilities:
1. HMAC-SHA256 Baseline Sealing: Generates a cryptographically strong signature
   over baseline telemetry files (persistence autoruns and LAN network state).
2. Machine-Sealed Key Derivation: Uses data/.sentinel_key (32 CSPRNG bytes) so
   signatures cannot be forged by external scripts or standard userland malware.
3. Anti-Tampering Detection: Detects if any persistence registry autorun baseline
   or gateway ARP baseline has been modified, appended, or tampered with offline.
================================================================================
"""

import os
import hmac
import json
import hashlib
from typing import Dict, Any, Optional, Tuple


def _get_sentinel_key(data_dir: str) -> bytes:
    """Retrieves or generates a machine-sealed 256-bit Sentinel signing key."""
    key_file = os.path.join(data_dir, ".sentinel_key")
    if os.path.exists(key_file):
        try:
            with open(key_file, "rb") as f:
                key = f.read()
                if len(key) == 32:
                    return key
        except Exception:
            pass
    key = os.urandom(32)
    try:
        with open(key_file, "wb") as f:
            f.write(key)
    except Exception:
        pass
    return key


class BaselineIntegrity:
    """Provides cryptographic signing and anti-tamper verification for baselines."""

    @classmethod
    def save_signed_json(cls, filepath: str, data: Dict[str, Any], data_dir: Optional[str] = None) -> str:
        """Saves a JSON file and writes an accompanying HMAC-SHA256 signature."""
        if not data_dir:
            data_dir = os.path.dirname(os.path.abspath(filepath))
        key = _get_sentinel_key(data_dir)

        # Canonical deterministic JSON encoding
        canonical_bytes = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')

        # Compute HMAC
        signature = hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()

        # Write data file
        with open(filepath, "wb") as f:
            f.write(canonical_bytes)

        # Write signature file
        sig_file = filepath + ".sig"
        with open(sig_file, "w", encoding="utf-8") as f:
            f.write(signature)

        return signature

    @classmethod
    def load_signed_json(cls, filepath: str, data_dir: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Loads and cryptographically verifies a signed JSON baseline file.
        Returns: (data_dict, status_string)
        Status values:
          'VERIFIED' - Signature matches cryptographically.
          'UNSIGNED' - File exists but has no signature (needs initial migration).
          'TAMPERED' - Signature exists but does NOT match! Critical tamper alert!
          'MISSING'  - File does not exist.
        """
        if not os.path.exists(filepath):
            return None, "MISSING"

        if not data_dir:
            data_dir = os.path.dirname(os.path.abspath(filepath))
        key = _get_sentinel_key(data_dir)

        sig_file = filepath + ".sig"
        has_sig = os.path.exists(sig_file)

        try:
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
            data = json.loads(raw_bytes.decode('utf-8'))
        except Exception:
            return None, "CORRUPT"

        if not has_sig:
            return data, "UNSIGNED"

        try:
            with open(sig_file, "r", encoding="utf-8") as f:
                expected_sig = f.read().strip()
        except Exception:
            return None, "TAMPERED"

        # Canonicalize and verify
        canonical_bytes = json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')
        computed_sig = hmac.new(key, canonical_bytes, hashlib.sha256).hexdigest()

        if hmac.compare_digest(computed_sig, expected_sig):
            return data, "VERIFIED"
        else:
            return None, "TAMPERED"
