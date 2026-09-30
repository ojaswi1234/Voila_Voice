import os
import json
import time
import math
import re
from typing import Dict, List, Tuple, Any

import ctypes
def _acquire_aegis():
    try:
        m = ctypes.windll.kernel32.CreateMutexW(None, False, "VoilaAegisMutex")
        ctypes.windll.kernel32.WaitForSingleObject(m, 0xFFFFFFFF)
        return m
    except: return None
def _release_aegis(m):
    if m:
        try: ctypes.windll.kernel32.ReleaseMutex(m)
        except: pass


class StaticRules:
DANGEROUS_CMDS = [
        r"rm\s+-rf", r"del\s+/f", r"format\s+[a-z]:", r"drop\s+table",
        r"invoke-webrequest", r"net\s+user", r"net\s+localgroup",
        r"reg\s+add", r"reg\s+delete", r"taskkill\s+/f"
    ]
    DANGEROUS_PATHS = [
        r"c:\\windows", r"c:\\program files", r"\\system32",
        r"\\appdata\\roaming\\microsoft"
    ]
    SENSITIVE_WINDOWS = [
        "password", "bitwarden", "1password", "lastpass", 
        "bank", "paypal", "crypto", "wallet", "settings"
    ]

    @classmethod
    def check_payload(cls, action_type: str, payload: str, window_title: str):
        wt_lower = (window_title or "").lower()
        pl_lower = (payload or "").lower()
        
        for sens in cls.SENSITIVE_WINDOWS:
            if sens in wt_lower:
                return False, f"Sensitive window detected: {sens}"
                
        if action_type in ("run_terminal", "type_keys"):
            for pattern in cls.DANGEROUS_CMDS:
                if re.search(pattern, pl_lower):
                    return False, f"Dangerous pattern matched: {pattern}"
                    
        if action_type in ("write_file", "delete_file", "edit_file"):
            for pattern in cls.DANGEROUS_PATHS:
                if re.search(pattern, pl_lower):
                    return False, f"Dangerous system path modification: {pattern}"
                    
        return True, ""


class DynamicMarkov:
    """
    Learns valid action sequences (A -> B) over time.
    If an agent tries a sequence that has never been seen or is highly improbable, flags it.
    """
    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self.transitions: Dict[str, Dict[str, int]] = {}
        self.state_counts: Dict[str, int] = {}
        self.last_state = "START"
        self.load()

    def load(self):
        m = _acquire_aegis()
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    self.transitions = data.get("transitions", {})
                    self.state_counts = data.get("state_counts", {})
        except Exception: pass
        finally: _release_aegis(m)
                
    def save(self):
        m = _acquire_aegis()
        try:
            with open(self.cache_file, "w") as f:
                json.dump({"transitions": self.transitions, "state_counts": self.state_counts}, f)
        except Exception: pass
        finally: _release_aegis(m)

    def observe(self, current_state: str):
        if self.last_state not in self.transitions:
            self.transitions[self.last_state] = {}
        self.transitions[self.last_state][current_state] = self.transitions[self.last_state].get(current_state, 0) + 1
        self.state_counts[self.last_state] = self.state_counts.get(self.last_state, 0) + 1
        self.last_state = current_state
        self.save()

    def get_probability(self, current_state: str) -> float:
        if self.last_state not in self.transitions or self.state_counts.get(self.last_state, 0) == 0:
            return 1.0 # Unknown states are given benefit of doubt initially (exploration)
            
        count = self.transitions[self.last_state].get(current_state, 0)
        total = self.state_counts[self.last_state]
        
        # Add smoothing so we don't return 0
        return (count + 1) / (total + len(self.transitions.get(self.last_state, {})) + 1)


class DynamicZScore:
    """
    Statistical anomaly detection (Lightweight).
    Maintains moving average and variance for features.
    """
    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self.stats = {} # feature_name -> {"mean": 0, "var": 0, "count": 0}
        self.load()

    def load(self):
        m = _acquire_aegis()
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    self.stats = json.load(f)
        except Exception: pass
        finally: _release_aegis(m)

    def save(self):
        m = _acquire_aegis()
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.stats, f)
        except Exception: pass
        finally: _release_aegis(m)

    def observe(self, feature_name: str, value: float) -> float:
        if feature_name not in self.stats:
            self.stats[feature_name] = {"mean": value, "var": 0.0, "count": 1}
            self.save()
            return 0.0 # Z-score 0 for first item

        s = self.stats[feature_name]
        count = s["count"]
        mean = s["mean"]
        var = s["var"]

        # Calculate Z-score BEFORE updating
        std_dev = math.sqrt(var) if var > 0 else 1.0
        z_score = abs(value - mean) / std_dev

        # Update moving average and variance (Welford's online algorithm)
        count += 1
        new_mean = mean + (value - mean) / count
        new_var = var + ((value - mean) * (value - new_mean) - var) / count

        self.stats[feature_name] = {"mean": new_mean, "var": new_var, "count": count}
        self.save()
        
        return z_score


class AegisMonitor:
    def __init__(self, data_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.markov = DynamicMarkov(os.path.join(data_dir, "aegis_markov.json"))
        self.zscore = DynamicZScore(os.path.join(data_dir, "aegis_zscore.json"))
        self.action_history = []
        self.last_action_time = time.time()
        self.risk_score = 0.0
        
        # Caching rejected actions (Hash-based)
        self.rejection_cache_file = os.path.join(data_dir, "aegis_rejections.json")
        self.rejections = set()
        if os.path.exists(self.rejection_cache_file):
            try:
                with open(self.rejection_cache_file, "r") as f:
                    self.rejections = set(json.load(f))
            except Exception: pass

    def _cache_rejection(self, action_id: str):
        self.rejections.add(action_id)
        if len(self.rejections) > 1000:
            # Randomly pop an item (sets don't have pop(index))
            self.rejections.pop()
        m = _acquire_aegis()
        try:
            with open(self.rejection_cache_file, "w") as f:
                json.dump(list(self.rejections), f)
        except Exception: pass
        finally: _release_aegis(m)

    def verify_action(self, action_type: str, payload: str, window_title: str) -> Tuple[bool, str]:
        """
        Main entry point to verify if an action is safe.
        Returns (is_safe, reason).
        """
        action_id = f"{action_type}|{payload}|{window_title}"
        if action_id in self.rejections:
            return False, "Action cached as malicious from previous rejection."

        # 1. Static Guardrails
        is_safe, reason = StaticRules.check_payload(action_type, payload, window_title)
        if not is_safe:
            self._cache_rejection(action_id)
            return False, reason

        # 2. Tool-Specific Rate Limiting (Z-Score on Time Delta)
        now = time.time()
        
        if not hasattr(self, 'last_tool_times'):
            self.last_tool_times = {}
            
        last_time = self.last_tool_times.get(action_type, now - 10.0)
        time_delta = now - last_time
        self.last_tool_times[action_type] = now
        self.last_action_time = now 
        
        # Isolate the Z-score feature per tool so fast/slow tools don't dilute each other!
        z_time = self.zscore.observe(f"time_delta_{action_type}", time_delta)
        if z_time > 4.0 and time_delta < 0.1: 
            self.risk_score += 20.0
        else:
            self.risk_score = max(0.0, self.risk_score - 1.0)

        # 3. Z-Score on Payload Size (Already isolated per tool)
        payload_len = len(payload or "")
        z_payload = self.zscore.observe(f"payload_len_{action_type}", payload_len)
        if z_payload > 5.0:
            self.risk_score += 15.0

        # 4. Markov Chain Context (Hallucination / Loop detection)
        prob = self.markov.get_probability(action_type)
        if prob < 0.05:
            # Highly unusual action transition
            self.risk_score += 30.0
            
        self.markov.observe(action_type)

        # 5. Risk Assessment
        if self.risk_score > 80.0:
            self._cache_rejection(action_id)
            return False, f"Dynamic Risk Score exceeded threshold (Score: {self.risk_score:.1f})"

        return True, "Safe"
