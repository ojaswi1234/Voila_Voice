"""
================================================================================
Voila Sentinel - Cross-Node Threat Alert Dispatcher & Plasma Trigger
================================================================================
Capabilities:
1. Visual Plasma Hazard Flare:
   Sends UDP IPC 'STATE:SECURITY_HAZARD' to 127.0.0.1:19885 to pulse monitor
   edges in intense coronal crimson and amber flames on active threat detection.
2. Cloud Backend Incident Relay:
   Authenticates using PBKDF2-HMAC-SHA256 (matching Go hashPhrase) and relays
   the threat event to POST /webhook/alert on the cloud backend.
3. Mobile Push Fanout:
   The cloud backend receives the alert, puts it in the circular ring buffer,
   and dispatches high-priority Firebase Cloud Messaging (FCM) push alerts
   to the user's mobile device.
4. Forensic Incident Audit Logging:
   Appends detailed JSONL forensic records to data/sentinel_incidents.jsonl.
================================================================================
"""

import os
import sys
import json
import time
import socket
import hashlib
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

PLASMA_PORT = 19885


def notify_plasma_border(state: str, port: int = PLASMA_PORT) -> bool:
    """Sends a state transition datagram to the plasma glow border overlay."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.sendto(f"STATE:{state}".encode("utf-8"), ("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False


def compute_secret_hash(phrase: str, device_id: str) -> str:
    """Computes PBKDF2-HMAC-SHA256 hash matching Go local-agent hashPhrase."""
    salt = (device_id + "_voila_salt_v2").encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", phrase.encode("utf-8"), salt, 10000, 32).hex()


class AlertDispatcher:
    """Orchestrates visual hazard glow, cloud relaying, and forensic logging."""

    def __init__(self, data_dir: Optional[str] = None):
        if not data_dir:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.incidents_log = os.path.join(data_dir, "sentinel_incidents.jsonl")

    def _load_connection_data(self) -> Optional[Dict[str, Any]]:
        agent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(agent_dir, "connection_data.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def log_incident(self, incident: Dict[str, Any]):
        """Persists incident to forensic JSONL append-only log."""
        try:
            with open(self.incidents_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(incident) + "\n")
        except Exception:
            pass

    def dispatch(
        self,
        threat_type: str,
        description: str,
        severity: str = "high",
        trip_circuit: bool = False,
        incident_details: Optional[Dict[str, Any]] = None,
        trigger_plasma: bool = True
    ) -> Dict[str, Any]:
        """
        Dispatches a threat incident across visual, cloud, and forensic layers.
        """
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        sev_upper = severity.upper()

        # 1. Trigger Visual Plasma Hazard Glow on Critical / High alerts
        plasma_triggered = False
        if trigger_plasma and sev_upper in ("CRITICAL", "HIGH"):
            plasma_triggered = notify_plasma_border("SECURITY_HAZARD")

        # 2. Build incident record
        incident = {
            "timestamp": timestamp,
            "threat_type": threat_type,
            "severity": sev_upper,
            "description": description,
            "trip_circuit": trip_circuit,
            "plasma_visual_alert": plasma_triggered,
            "details": incident_details or {}
        }

        # 3. Cloud Relay to Backend & Mobile FCM
        cloud_relay_status = "NOT_CONFIGURED"
        cloud_response_code = None

        conn_data = self._load_connection_data()
        if conn_data and conn_data.get("connected"):
            backend_url = conn_data.get("backend_url", "").rstrip("/")
            device_id = conn_data.get("device_id", "")
            security_phrase = conn_data.get("security_phrase", "")

            if backend_url and device_id and security_phrase:
                secret_hash = compute_secret_hash(security_phrase, device_id)
                alert_payload = {
                    "device_id": device_id,
                    "secret_hash": secret_hash,
                    "alert_type": threat_type,
                    "source_ip": "127.0.0.1",
                    "description": description,
                    "severity": severity.lower(),
                    "trip_circuit": trip_circuit
                }

                url = f"{backend_url}/webhook/alert"
                req_data = json.dumps(alert_payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers={"Content-Type": "application/json", "User-Agent": "VoilaSentinel/1.0"}
                )

                try:
                    with urllib.request.urlopen(req, timeout=3.5) as resp:
                        cloud_response_code = resp.status
                        if resp.status == 200:
                            cloud_relay_status = "DELIVERED_TO_BACKEND_AND_MOBILE"
                        else:
                            cloud_relay_status = f"BACKEND_HTTP_{resp.status}"
                except urllib.error.HTTPError as he:
                    cloud_response_code = he.code
                    cloud_relay_status = f"BACKEND_HTTP_{he.code}"
                except Exception as e:
                    cloud_relay_status = f"OFFLINE_UNREACHABLE ({type(e).__name__})"

        incident["cloud_relay_status"] = cloud_relay_status
        incident["cloud_response_code"] = cloud_response_code

        # 4. Forensic log
        self.log_incident(incident)

        return incident


# Global Singleton
alert_dispatcher = AlertDispatcher()
