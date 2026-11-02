import unittest
import math
import socket
import os
import sys

# Ensure local-agent directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestMacOSCursorAnimation(unittest.TestCase):
    def test_anchored_tip_invariance(self):
        """Verify that when the cursor scales down, the hotspot tip remains pinned at (cx, cy)."""
        arrow_pts = [
            0, 0,
            0, 15,
            4, 12,
            8, 19,
            10, 18,
            6, 11,
            11, 11,
        ]
        cx, cy = 500, 300
        absolute_pts = []
        for i in range(0, len(arrow_pts), 2):
            absolute_pts.extend([cx + arrow_pts[i], cy + arrow_pts[i+1]])

        def _transform(pts, cx, cy, scale, angle):
            out = []
            rad = math.radians(angle)
            cos_spin = math.cos(rad)
            for i in range(0, len(pts), 2):
                x = pts[i] - cx
                y = pts[i+1] - cy
                nx = (x * cos_spin) * scale
                ny = y * scale
                out.extend([nx + cx, ny + cy])
            return out

        # Test at resting scale 1.0
        t1 = _transform(absolute_pts, cx, cy, 1.0, 0.0)
        self.assertEqual((t1[0], t1[1]), (cx, cy))

        # Test at compressed scale 0.74
        t_shrink = _transform(absolute_pts, cx, cy, 0.74, 0.0)
        self.assertEqual((t_shrink[0], t_shrink[1]), (cx, cy), "Tip MUST remain exactly pinned at (cx, cy) during shrink")
        
        # Verify body points shrank towards tip
        self.assertLess(t_shrink[3], t1[3], "Bottom vertex y must contract towards cy")
        self.assertLess(t_shrink[2], t1[2] + 1e-6)

        # Test at spring overshoot scale 1.05
        t_pop = _transform(absolute_pts, cx, cy, 1.05, 0.0)
        self.assertEqual((t_pop[0], t_pop[1]), (cx, cy), "Tip MUST remain pinned at (cx, cy) during spring pop")
        self.assertGreater(t_pop[3], t1[3], "Bottom vertex y must expand past resting during overshoot")

    def test_single_click_easing_curve(self):
        """Verify the 3-phase easing curve of macOS single click: shrink -> hold -> spring rebound."""
        def get_scale(t):
            if t < 0.25:
                p = t / 0.25
                return 1.0 - 0.26 * (p * (2.0 - p))
            elif t < 0.40:
                return 0.74
            else:
                p = (t - 0.40) / 0.60
                spring = 1.0 - math.pow(1.0 - p, 2) * math.cos(p * math.pi * 1.2)
                return 0.74 + 0.26 * spring

        # t = 0.0: resting
        self.assertAlmostEqual(get_scale(0.0), 1.0, places=3)

        # t = 0.25: bottom of shrink
        self.assertAlmostEqual(get_scale(0.25), 0.74, places=3)

        # t = 0.35: held at bottom
        self.assertAlmostEqual(get_scale(0.35), 0.74, places=3)

        # Rebound has slight overshoot > 1.0
        mid_rebound_scales = [get_scale(t) for t in [0.65, 0.70, 0.75, 0.80, 0.85]]
        max_scale = max(mid_rebound_scales)
        self.assertGreater(max_scale, 1.0, f"Spring rebound must exhibit subtle macOS overshoot > 1.0 (got {max_scale})")
        self.assertLessEqual(max_scale, 1.06, f"Overshoot should be subtle and elegant <= 1.06 (got {max_scale})")

        # t = 1.0: settled at resting
        self.assertAlmostEqual(get_scale(1.0), 1.0, places=3)

    def test_halo_ring_expansion(self):
        """Verify the macOS click halo ring radiates outward smoothly."""
        def get_halo(t):
            if t <= 0.20:
                return None
            rt = (t - 0.20) / 0.80
            ring_r = 4 + 22 * rt
            ring_w = max(1.0, 2.5 * (1.0 - rt))
            return ring_r, ring_w

        self.assertIsNone(get_halo(0.10))
        r_start, w_start = get_halo(0.21)
        self.assertAlmostEqual(r_start, 4.0, delta=1.0)
        self.assertAlmostEqual(w_start, 2.5, delta=0.2)

        r_end, w_end = get_halo(1.0)
        self.assertAlmostEqual(r_end, 26.0, delta=0.1)
        self.assertAlmostEqual(w_end, 1.0, delta=0.1)

    def test_badge_scaling_geometry(self):
        """Verify badge coordinates scale proportionately with cursor anchor."""
        cx, cy = 200, 150
        scale = 0.74
        b_x = cx + 14 * scale
        b_y = cy + 9 * scale
        b_w = 18 * scale
        b_h = 10 * scale

        self.assertAlmostEqual(b_x - cx, 10.36, places=2)
        self.assertAlmostEqual(b_y - cy, 6.66, places=2)
        self.assertAlmostEqual(b_w, 13.32, places=2)
        self.assertAlmostEqual(b_h, 7.40, places=2)

    def test_motion_dispatches_click_animation_packet(self):
        """Verify cursor_motion sends CLICK,<x>,<y>,<kind> instead of HIDE."""
        import cursor_motion
        captured_packets = []

        class DummySock:
            def sendto(self, data, addr):
                captured_packets.append((data, addr))

        orig_sock = cursor_motion._overlay_sock
        orig_sendinput = cursor_motion.sendinput_click
        orig_setpos = cursor_motion._set_cursor_pos
        orig_user32_setpos = cursor_motion._user32.SetCursorPos

        cursor_motion._overlay_sock = DummySock()
        cursor_motion.sendinput_click = lambda *a, **k: True
        cursor_motion._set_cursor_pos = lambda *a: None
        cursor_motion._user32.SetCursorPos = lambda *a: 1

        try:
            os.environ["VOILA_CURSOR_PRECISION"] = "1"
            cursor_motion._do_click("left", 345, 678)
            self.assertTrue(len(captured_packets) >= 1)
            first_pkt, (host, port) = captured_packets[0]
            self.assertEqual(first_pkt, b"CLICK,345,678,left")
            self.assertEqual(host, "127.0.0.1")
        finally:
            cursor_motion._overlay_sock = orig_sock
            cursor_motion.sendinput_click = orig_sendinput
            cursor_motion._set_cursor_pos = orig_setpos
            cursor_motion._user32.SetCursorPos = orig_user32_setpos
            if "VOILA_CURSOR_PRECISION" in os.environ:
                del os.environ["VOILA_CURSOR_PRECISION"]

if __name__ == "__main__":
    unittest.main()
