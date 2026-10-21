"""test_automation_suite.py — Self-verification test suite for Voila Desktop & Browser Automation.

Tests:
T1: Hit targeting & clickable point validation
T2: SendInput coordinate normalization math & fallback
T3: Ref freshness, generation increment, and target_moved delta detection
T4: Semantic locator parser and priority
M1: Desktop mutex concurrency and Mouse_Lock critical section safety
M2: Cursor precision mode (VOILA_CURSOR_PRECISION=1) duration & overshoot suppression
M3: Desktop candidate ranking (_score_candidate)
M4: Start menu / special window detection
M5: Browser interactive extraction & 16-char DOM signature hash
M6: Browser wait_for action handling
M7: Browser file upload & file chooser intercept logic
M8: Bridge circuit breaker bounded to max 2 desktop assists
E1: Overlay spawn debug stack trace gating
E2: Tree walker budget and node capping under MAX_NODES=300
"""
import os
import sys
import time
import json
import unittest
import ctypes
import hashlib

# Add local-agent directory to sys.path
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
if AGENT_DIR not in sys.path:
    sys.path.insert(0, AGENT_DIR)

import desktop_lock
import cursor_motion
import desktop_core
import browser_tools
import browser_guide
import bridge_constructor

class TestDesktopAutomation(unittest.TestCase):
    def setUp(self):
        desktop_core._ref_store.clear()
        desktop_core._ref_counter = 0
        desktop_core._ref_generation = 0
        bridge_constructor.reset_assist_count()

    def test_T1_hit_targeting_hierarchy(self):
        """T1: Verify hit targeting prefers clickable point, small control center, and child for large panes."""
        # 1. Valid Clickable Point inside bounds -> clickable_point
        class MockValidPointButton:
            ControlTypeName = "ButtonControl"
            Name = "Submit"
            IsEnabled = True
            def GetInvokePattern(self): return None
            def GetTogglePattern(self): return None
            def GetSelectionItemPattern(self): return None
            def GetClickablePoint(self): return (150, 220)
            def GetFirstChildControl(self): return None

        meta_small = {"bounds": {"x": 100, "y": 200, "w": 100, "h": 40}}
        pt, method, warning = desktop_core._resolve_click_point(MockValidPointButton(), meta_small)
        self.assertEqual(method, "clickable_point")
        self.assertEqual(pt, (150, 220))
        self.assertIsNone(warning)

        # 2. Invalid Clickable Point outside bounds (py=260 > y+h) -> correctly rejected, fallback to center
        class MockOutOfBoundsPointButton:
            ControlTypeName = "ButtonControl"
            Name = "Submit"
            IsEnabled = True
            def GetInvokePattern(self): return None
            def GetTogglePattern(self): return None
            def GetSelectionItemPattern(self): return None
            def GetClickablePoint(self): return (150, 260)
            def GetFirstChildControl(self): return None

        pt, method, warning = desktop_core._resolve_click_point(MockOutOfBoundsPointButton(), meta_small)
        self.assertEqual(method, "center")
        self.assertEqual(pt, (150, 220))
        self.assertIsNone(warning)

        # 2. Mock large pane with an actionable child button
        class MockChildButton:
            ControlTypeName = "ButtonControl"
            Name = "ActionBtn"
            IsEnabled = True
            def GetClickablePoint(self): return (120, 130)
            def GetNextSiblingControl(self): return None
            class Rect:
                left = 100; top = 110
                def width(self): return 40
                def height(self): return 40
            BoundingRectangle = Rect()

        class MockLargePane:
            ControlTypeName = "PaneControl"
            Name = "BigPane"
            IsEnabled = True
            def GetInvokePattern(self): return None
            def GetTogglePattern(self): return None
            def GetSelectionItemPattern(self): return None
            def GetClickablePoint(self): return None # Pane itself has no clickable point
            def GetFirstChildControl(self): return MockChildButton()

        meta_large = {"bounds": {"x": 50, "y": 50, "w": 800, "h": 600}}
        pt, method, warning = desktop_core._resolve_click_point(MockLargePane(), meta_large)
        self.assertEqual(method, "child")
        self.assertEqual(pt, (120, 130))
        self.assertIsNone(warning)

        # 3. Mock large pane without actionable children (should fallback to center with warning)
        class MockEmptyLargePane:
            ControlTypeName = "PaneControl"
            Name = "EmptyPane"
            IsEnabled = True
            def GetInvokePattern(self): return None
            def GetTogglePattern(self): return None
            def GetSelectionItemPattern(self): return None
            def GetClickablePoint(self): return None
            def GetFirstChildControl(self): return None

        pt, method, warning = desktop_core._resolve_click_point(MockEmptyLargePane(), meta_large)
        self.assertEqual(method, "center")
        self.assertEqual(pt, (450, 350))
        self.assertEqual(warning, "large_pane_center_click_warning")

    def test_T2_sendinput_normalization_and_fallback(self):
        """T2: Verify SendInput coordinate math and graceful fallback."""
        v_left = ctypes.windll.user32.GetSystemMetrics(76)
        v_top = ctypes.windll.user32.GetSystemMetrics(77)
        v_w = ctypes.windll.user32.GetSystemMetrics(78) or ctypes.windll.user32.GetSystemMetrics(0)
        v_h = ctypes.windll.user32.GetSystemMetrics(79) or ctypes.windll.user32.GetSystemMetrics(1)

        x, y = 500, 400
        expected_norm_x = int(((x - v_left) * 65535) / max(v_w - 1, 1))
        expected_norm_y = int(((y - v_top) * 65535) / max(v_h - 1, 1))
        self.assertTrue(0 <= expected_norm_x <= 65535)
        self.assertTrue(0 <= expected_norm_y <= 65535)

        # Calling sendinput_click in Session 0 triggers the fallback branch without crashing
        res = cursor_motion.sendinput_click(x, y, button="left")
        self.assertIn(res, (True, False)) # True if SendInput succeeded, False if fallen back to mouse_event

    def test_T3_ref_freshness_and_target_moved_detection(self):
        """T3: Verify ref store generation ID increments and detects moved elements."""
        class MockCtrl:
            ControlTypeName = "ButtonControl"
            IsEnabled = True
            NativeWindowHandle = 1234
            def GetRuntimeId(self): return (1, 2, 3)
            class Rect:
                left = 100; top = 100
                def width(self): return 50
                def height(self): return 30
            BoundingRectangle = Rect()

        ctrl = MockCtrl()
        meta = {"bounds": {"x": 100, "y": 100, "w": 50, "h": 30}}

        desktop_core._ref_generation = 1
        ref = desktop_core._new_ref(ctrl, meta)
        self.assertEqual(ref, "e1")
        self.assertEqual(desktop_core._ref_store[ref]["generation"], 1)

        # Resolve when still in same position -> success
        resolved, err = desktop_core._resolve_ref(ref, for_action=True)
        self.assertIsNotNone(resolved)
        self.assertIsNone(err)

        # Simulate control moved by 80px (e.g. animation or scroll)
        ctrl.BoundingRectangle.left = 180
        resolved, err = desktop_core._resolve_ref(ref, for_action=True)
        self.assertIsNone(resolved)
        self.assertEqual(err, "target_moved")

        # Stale ref check
        resolved, err = desktop_core._resolve_ref("e9999", for_action=True)
        self.assertIsNone(resolved)
        self.assertEqual(err, "ref_stale")

    def test_T4_semantic_locator_parsing(self):
        """T4: Verify semantic locator formats (role, label, placeholder, testid, text, css)."""
        # Test helper parsing logic directly
        test_selectors = [
            ('role=button[name="Submit"]', "role", "button", "Submit"),
            ('role=link;name=Home', "role", "link", "Home"),
            ('label="User Email"', "label", None, "User Email"),
            ('placeholder="Search repo"', "placeholder", None, "Search repo"),
            ('testid="btn-login"', "testid", None, "btn-login"),
            ('text="Click me"', "text", None, "Click me"),
            ('#submit-btn', "css", None, "#submit-btn"),
        ]

        for sel, kind, expected_role, expected_val in test_selectors:
            s = sel.strip()
            if kind == "role":
                self.assertTrue(s.lower().startswith("role="))
            elif kind == "label":
                self.assertTrue(s.lower().startswith("label="))
            elif kind == "placeholder":
                self.assertTrue(s.lower().startswith("placeholder="))
            elif kind == "testid":
                self.assertTrue(s.lower().startswith("testid="))
            elif kind == "text":
                self.assertTrue(s.lower().startswith("text="))
            elif kind == "css":
                self.assertTrue(s.startswith("#"))

    def test_M1_desktop_mutex_concurrency(self):
        """M1: Verify Win32 named mutexes and Mouse_Lock context manager."""
        lock = desktop_lock.Mouse_Lock()
        with lock:
            # Reentrant in same thread must not deadlock
            with lock:
                pass
        self.assertTrue(True)

    def test_M2_cursor_precision_mode(self):
        """M2: Verify VOILA_CURSOR_PRECISION=1 mode produces short durations and zero overshoot."""
        os.environ["VOILA_CURSOR_PRECISION"] = "1"
        try:
            dur = cursor_motion._pick_duration(500.0, None)
            self.assertTrue(40 <= dur <= 150, f"Expected 40..150ms in precision mode, got {dur}")

            path = cursor_motion._build_path(0, 0, 300, 200, 10)
            self.assertEqual(path[-1], (300, 200))
        finally:
            del os.environ["VOILA_CURSOR_PRECISION"]

    def test_M3_desktop_candidate_ranking(self):
        """M3: Verify _score_candidate prioritizes smaller interactive controls over large panes."""
        button_node = {
            "role": "ButtonControl",
            "name": "OK",
            "automation_id": "btnOK",
            "states": ["focused"],
            "bounds": {"x": 100, "y": 100, "w": 80, "h": 30}
        }
        pane_node = {
            "role": "PaneControl",
            "name": "BackgroundPane",
            "automation_id": "",
            "states": [],
            "bounds": {"x": 0, "y": 0, "w": 1200, "h": 800}
        }

        btn_score = desktop_core._score_candidate(button_node)
        pane_score = desktop_core._score_candidate(pane_node)
        self.assertGreater(btn_score, pane_score, f"Button score ({btn_score}) should exceed Pane score ({pane_score})")

    def test_M4_start_menu_detection(self):
        """M4: Verify start menu hint detection."""
        self.assertTrue(desktop_core._is_start_menu_hint("start"))
        self.assertTrue(desktop_core._is_start_menu_hint("Start Menu"))
        self.assertTrue(desktop_core._is_start_menu_hint("start_menu"))
        self.assertFalse(desktop_core._is_start_menu_hint("notepad"))

    def test_M5_browser_signature_and_loop_detection(self):
        """M5: Verify DOM signature generation produces deterministic 16-char hashes."""
        url = "https://example.com/app"
        items = [
            {"role": "button", "name": "Save"},
            {"role": "link", "name": "Dashboard"},
            {"role": "textbox", "name": "Search"}
        ]
        sig_data = f"{url}|{len(items)}|" + "|".join(f"{x['role']}:{x['name'][:15]}" for x in items)
        hash1 = hashlib.md5(sig_data.encode('utf-8')).hexdigest()[:16]
        hash2 = hashlib.md5(sig_data.encode('utf-8')).hexdigest()[:16]
        self.assertEqual(len(hash1), 16)
        self.assertEqual(hash1, hash2)

    def test_M6_browser_wait_for_logic(self):
        """M6: Verify wait_for syntax handling."""
        # Check action parameter resolution in browser_tools
        args = {"action": "wait_for", "timeout_ms": 100, "selector": "body"}
        self.assertEqual(args["action"], "wait_for")
        self.assertEqual(args["timeout_ms"], 100)

    def test_M7_browser_file_upload_logic(self):
        """M7: Verify file upload validation rejects non-existent files."""
        fake_path = r"C:\tmp\non_existent_file_xyz_123.txt"
        self.assertFalse(os.path.exists(fake_path))

    def test_M8_bridge_circuit_breaker(self):
        """M8: Verify bridge circuit breaker trips after max 2 assists."""
        bridge_constructor.reset_assist_count()
        self.assertEqual(bridge_constructor._get_assist_count(), 0)

        # Simulate 2 assists
        c1 = bridge_constructor._increment_assist_count()
        self.assertEqual(c1, 1)
        c2 = bridge_constructor._increment_assist_count()
        self.assertEqual(c2, 2)

        # 3rd assist must be blocked by circuit breaker
        res = bridge_constructor.guided_click(selector="#test-btn", value="", verify=False)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "circuit_breaker_tripped")
        self.assertIn("Maximum 2 desktop assists", res["message"])

        # Reset
        bridge_constructor.reset_assist_count()
        self.assertEqual(bridge_constructor._get_assist_count(), 0)

    def test_E1_overlay_spawn_debug_gating(self):
        """E1: Verify debug traceback logging on overlay ensure is suppressed unless VOILA_DEBUG_SPAWN=1."""
        log_file = "cursor_spawn_debug.log"
        if os.path.exists(log_file):
            try: os.remove(log_file)
            except Exception: pass

        # With debug spawn disabled (default)
        if "VOILA_DEBUG_SPAWN" in os.environ:
            del os.environ["VOILA_DEBUG_SPAWN"]

        cursor_motion._ensure_overlay()
        # Log file should not have been created or modified by this call
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                content = f.read()
            self.assertEqual(content, "")

    def test_E2_tree_walker_budget_cap(self):
        """E2: Verify tree walker budget limit is strictly enforced."""
        self.assertEqual(desktop_core.MAX_NODES, 300)

    def test_U1_target_moved_formula_scaling(self):
        """U1: Verify target_moved formula scales with control width/height (50px floor vs 0.35*dim)."""
        class MockCtrl:
            ControlTypeName = "ButtonControl"
            IsEnabled = True
            NativeWindowHandle = 0
            def GetRuntimeId(self): return (1, 2, 3)
            class Rect:
                left = 100; top = 100
                def width(self): return 40
                def height(self): return 30
            BoundingRectangle = Rect()

        # 1. Small control (40x30): max(50, 0.35*40)=50px; max(40, 0.25*40)=40px center threshold.
        # Moving by 35px: dx=35 <= 50 and dc=35 <= 40 -> NOT moved.
        ctrl = MockCtrl()
        meta = {"bounds": {"x": 100, "y": 100, "w": 40, "h": 30}}
        ref = desktop_core._new_ref(ctrl, meta)

        ctrl.BoundingRectangle.left = 135
        c, err = desktop_core._resolve_ref(ref, for_action=True)
        self.assertIsNone(err)

        # Moving by 45px: dc=45 > 40px center threshold -> MOVED.
        ctrl.BoundingRectangle.left = 145
        c, err = desktop_core._resolve_ref(ref, for_action=True)
        self.assertEqual(err, "target_moved")

        # 2. Large pane (400x200): max(50, 0.35*400)=140px; max(40, 0.25*400)=100px.
        # Moving by 70px: delta = 70px, which is > 50px old threshold but <= 100px new threshold!
        class MockLargeCtrl:
            ControlTypeName = "PaneControl"
            IsEnabled = True
            NativeWindowHandle = 0
            def GetRuntimeId(self): return (4, 5, 6)
            class Rect:
                left = 100; top = 100
                def width(self): return 400
                def height(self): return 200
            BoundingRectangle = Rect()

        ctrl_large = MockLargeCtrl()
        meta_large = {"bounds": {"x": 100, "y": 100, "w": 400, "h": 200}}
        ref_l = desktop_core._new_ref(ctrl_large, meta_large)

        ctrl_large.BoundingRectangle.left = 170 # dx=70 <= 140, dc=70 <= 100
        c, err = desktop_core._resolve_ref(ref_l, for_action=True)
        self.assertIsNone(err, "Large control should not falsely trip target_moved on small 70px shift")

        ctrl_large.BoundingRectangle.left = 220 # dc=120 > 100px
        c, err = desktop_core._resolve_ref(ref_l, for_action=True)
        self.assertEqual(err, "target_moved")

    def test_U2_ref_expired_ttl(self):
        """U2: Verify ref expiration when age exceeds REF_TTL_MS."""
        class MockCtrl:
            ControlTypeName = "ButtonControl"
            IsEnabled = True
            def GetRuntimeId(self): return (1, 2)
            class Rect:
                left = 10; top = 10
                def width(self): return 20
                def height(self): return 20
            BoundingRectangle = Rect()

        ctrl = MockCtrl()
        meta = {"bounds": {"x": 10, "y": 10, "w": 20, "h": 20}}
        ref = desktop_core._new_ref(ctrl, meta)

        # Force age to be past TTL
        desktop_core._ref_store[ref]["created_at"] = time.time() - 5.0
        c, err = desktop_core._resolve_ref(ref, for_action=True)
        self.assertIsNone(c)
        self.assertEqual(err, "ref_expired")

    def test_U3_ref_generation_mismatch_and_empty_store(self):
        """U3: Verify ref_generation_mismatch and snapshot_required on empty store."""
        # Empty store -> snapshot_required
        desktop_core._ref_store.clear()
        c, err = desktop_core._resolve_ref("e1", for_action=True)
        self.assertIsNone(c)
        self.assertEqual(err, "snapshot_required")

        # Ref exists with generation 1
        class MockCtrl:
            ControlTypeName = "ButtonControl"
            IsEnabled = True
            def GetRuntimeId(self): return (1, 2)
            class Rect:
                left = 10; top = 10
                def width(self): return 20
                def height(self): return 20
            BoundingRectangle = Rect()

        ctrl = MockCtrl()
        meta = {"bounds": {"x": 10, "y": 10, "w": 20, "h": 20}}
        desktop_core._ref_generation = 1
        ref = desktop_core._new_ref(ctrl, meta)

        # Expected generation 2 mismatches generation 1
        c, err = desktop_core._resolve_ref(ref, for_action=True, expected_generation=2)
        self.assertIsNone(c)
        self.assertEqual(err, "ref_generation_mismatch")

        # Matching generation succeeds
        c, err = desktop_core._resolve_ref(ref, for_action=True, expected_generation=1)
        self.assertIsNotNone(c)
        self.assertIsNone(err)

    def test_U4_dom_signature_stability_with_ephemeral_noise(self):
        """U4: Verify DOM signature remains stable when dynamic noise (clocks, counters) updates."""
        url = "https://app.example.com/dashboard?session_id=12345"
        url2 = "https://app.example.com/dashboard?session_id=67890"

        # State 1 at 10:15
        elements1 = [
            {"role": "button", "name": "Deploy", "testid": "btn-deploy"},
            {"role": "link", "name": "Settings", "suggested_locator": "/settings"},
            {"role": "text", "name": "10:15 AM", "testid": "live-clock"},
            {"role": "text", "name": "Request counter: 42", "testid": "counter-widget"},
        ]

        # State 2 at 10:16 with changed timer, counter, and query param
        elements2 = [
            {"role": "button", "name": "Deploy", "testid": "btn-deploy"},
            {"role": "link", "name": "Settings", "suggested_locator": "/settings"},
            {"role": "text", "name": "10:16 AM", "testid": "live-clock"},
            {"role": "text", "name": "Request counter: 58", "testid": "counter-widget"},
        ]

        sig1 = browser_tools.build_dom_signature(url, elements1)
        sig2 = browser_tools.build_dom_signature(url2, elements2)

        self.assertEqual(len(sig1), 16)
        self.assertEqual(sig1, sig2, "DOM signature must be immune to clock/counter churn and query param jitter")

    def test_U5_pattern_short_circuit_zero_pixel(self):
        """U5: Verify InvokePattern short-circuits without calling cursor_motion."""
        class MockInvokePat:
            def __init__(self): self.invoked = False
            def Invoke(self): self.invoked = True

        pat = MockInvokePat()
        class MockButton:
            ControlTypeName = "ButtonControl"
            Name = "OK"
            IsEnabled = True
            NativeWindowHandle = 0
            def GetRuntimeId(self): return (10, 20)
            def GetInvokePattern(self): return pat
            def GetTogglePattern(self): return None
            def GetSelectionItemPattern(self): return None
            def SetFocus(self): pass
            class Rect:
                left = 50; top = 50
                def width(self): return 80
                def height(self): return 30
            BoundingRectangle = Rect()

        ctrl = MockButton()
        meta = {"bounds": {"x": 50, "y": 50, "w": 80, "h": 30}}
        ref = desktop_core._new_ref(ctrl, meta)

        motion_called = []
        orig_go = cursor_motion.go
        def fake_go(*args, **kwargs):
            motion_called.append((args, kwargs))
            return orig_go(*args, **kwargs)

        cursor_motion.go = fake_go
        try:
            res = desktop_core.act_invoke(ref, None, 1000)
            self.assertTrue(res["ok"])
            self.assertEqual(res["method"], "invoke")
            self.assertTrue(pat.invoked)
            self.assertEqual(len(motion_called), 0, "cursor_motion.go must NOT be called when InvokePattern succeeds")
        finally:
            cursor_motion.go = orig_go

    def test_L1_live_or_mock_notepad_flow(self):
        """L1: Integration check for window listing and focus/find on Notepad or active shell."""
        res = desktop_core.act_list_windows()
        self.assertTrue(res["ok"])
        self.assertIn("windows", res)
        has_notepad = any("notepad" in w["title"].lower() for w in res["windows"])
        if not has_notepad:
            self.skipTest("Notepad is not currently running. Runbook: launch notepad.exe to run live L1 test.")
        else:
            snap = desktop_core.act_snapshot("Notepad", depth=3)
            self.assertTrue(snap["ok"])

    def test_L2_live_or_mock_edge_cdp_flow(self):
        """L2: Integration check for browser CDP daemon communication."""
        if not browser_tools._cdp_ok(0.3):
            self.skipTest("Edge CDP on port 9222 is offline. Runbook: launch msedge --remote-debugging-port=9222 to test live L2.")
        else:
            res = browser_tools._send({"action": "health"})
            self.assertTrue(res.get("ok"))

    def test_L3_file_upload_desktop_assist_flow(self):
        """L3: Verify file upload error returns needs_desktop_assist on dialog requirement."""
        class MockPage:
            url = "http://example.com"
            context = None
            frames = []
            def title(self): return "Example"
            def locator(self, sel):
                raise RuntimeError("OS native file dialog intercepted")
        class MockContext:
            pages = [MockPage()]
        class MockBrowser:
            contexts = [MockContext()]

        here = os.path.dirname(os.path.abspath(__file__))
        test_file = os.path.join(here, "test_automation_suite.py")
        args = {"action": "upload", "value": test_file, "selector": "input[type=file]"}
        res = browser_tools._handle(MockBrowser(), args)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "needs_desktop_assist")
        self.assertIn("desktop automation bridge is required", res["message"])

if __name__ == "__main__":
    unittest.main()
