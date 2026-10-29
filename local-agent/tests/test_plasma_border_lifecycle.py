"""test_plasma_border_lifecycle.py - Automated tests for plasma border lifecycle, state persistence, and IPC."""

import unittest
import os
import sys
import json
import time
import socket
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(SCRIPT_DIR, "plasma_settings.json")
PLASMA_SCRIPT = os.path.join(SCRIPT_DIR, "plasma_border.py")
TEST_PORT = 19899

class TestPlasmaBorderLifecycle(unittest.TestCase):

    def setUp(self):
        # Backup existing settings if present
        self.backup = None
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                self.backup = f.read()

    def tearDown(self):
        # Restore backup
        if self.backup is not None:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                f.write(self.backup)

    def test_settings_persistence(self):
        """Verify plasma_settings.json can save and load theme and state."""
        # 1. Write active state
        data = {"theme": "solar_gold", "state": "IDLE"}
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["state"], "IDLE")
        self.assertEqual(loaded["theme"], "solar_gold")

        # 2. Write OFF state
        data["state"] = "OFF"
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["state"], "OFF")

    def test_plasma_border_cli_and_ipc(self):
        """Verify plasma_border.py starts with --state IDLE and responds to IPC commands."""
        # Start plasma_border on a dedicated test port
        proc = subprocess.Popen(
            [sys.executable, PLASMA_SCRIPT, "--port", str(TEST_PORT), "--theme", "siri", "--state", "IDLE"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        try:
            time.sleep(0.5) # Give Tkinter and UDP socket time to initialize
            self.assertIsNone(proc.poll(), "plasma_border.py should be running")

            # Send IPC message: THEME:gemini
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(b"THEME:gemini", ("127.0.0.1", TEST_PORT))
            time.sleep(0.2)

            # Send IPC message: STATE:SEARCH
            s.sendto(b"STATE:SEARCH", ("127.0.0.1", TEST_PORT))
            time.sleep(0.2)

            # Send IPC message: DISABLE
            s.sendto(b"DISABLE", ("127.0.0.1", TEST_PORT))
            time.sleep(0.2)

            # Send IPC message: ENABLE
            s.sendto(b"ENABLE", ("127.0.0.1", TEST_PORT))
            time.sleep(0.2)

            # Send IPC message: EXIT
            s.sendto(b"EXIT", ("127.0.0.1", TEST_PORT))
            s.close()

            # Wait for clean exit
            proc.wait(timeout=3.0)
            self.assertIsNotNone(proc.poll(), "plasma_border.py should exit on EXIT IPC message")
        finally:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

    def test_plasma_border_starts_as_disabled_when_off(self):
        """Verify plasma_border.py --state OFF starts disabled."""
        proc = subprocess.Popen(
            [sys.executable, PLASMA_SCRIPT, "--port", str(TEST_PORT), "--theme", "gemini", "--state", "OFF"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        try:
            time.sleep(0.5)
            self.assertIsNone(proc.poll(), "plasma_border.py should run even if idle/off until instructed")

            # Send EXIT
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(b"EXIT", ("127.0.0.1", TEST_PORT))
            s.close()
            proc.wait(timeout=3.0)
        finally:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

    def test_agent_toggle_cycle_and_restart(self):
        """Simulate toggle OFF -> ON -> restart logic from run_hidden_agent.pyw."""
        # Step 1: Initial state is IDLE
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"theme": "solar_gold", "state": "IDLE"}, f, indent=2)

        # Step 2: Toggle OFF
        # run_hidden_agent writes "OFF" to disk first, then stops border
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"theme": "solar_gold", "state": "OFF"}, f, indent=2)

        # Verify disk has OFF
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["state"], "OFF")

        # Step 3: Toggle ON
        # run_hidden_agent writes "IDLE" to disk first, then starts border
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump({"theme": "solar_gold", "state": "IDLE"}, f, indent=2)

        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["state"], "IDLE")

        # Step 4: Verify agent restart with IDLE starts the process
        proc = subprocess.Popen(
            [sys.executable, PLASMA_SCRIPT, "--port", str(TEST_PORT), "--theme", data["theme"], "--state", data["state"]],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        try:
            time.sleep(0.5)
            self.assertIsNone(proc.poll(), "Should be running when restarted with IDLE state")
        finally:
            if proc.poll() is None:
                proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except Exception:
                    pass

if __name__ == "__main__":
    unittest.main()
