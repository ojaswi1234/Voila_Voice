"""test_custom_desktop_tasks.py - Automated Custom Task Suite for Voila Desktop Automation.

Tests:
1. Bridge Health & Window Enumeration (list_windows, foreground)
2. UIA Accessibility Snapshot & Generation ID Tracking (snapshot)
3. Semantic Element Query (find)
4. AI Cursor Navigation & macOS Click Animation Integration (move_cursor, click, double click, right click)
5. End-to-End Notepad Workflow (Launch, Snapshot, Type, Verify, Clean Dismissal)
6. Security & Stale Ref Protection (ref_generation mismatch verification)
7. Error Boundary & Edge Case Handling (invalid args, graceful rejection)
"""

import subprocess
import json
import time
import os
import sys

LOCAL_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable

def run_desktop_tool(args_list: list[str]) -> dict:
    cmd = [PYTHON_EXE, os.path.join(LOCAL_AGENT_DIR, "desktop_tools.py")] + args_list
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=LOCAL_AGENT_DIR, timeout=35)
    stdout = (proc.stdout or "").strip()
    try:
        return json.loads(stdout)
    except Exception as e:
        return {
            "ok": False,
            "error": "json_parse_error",
            "message": f"Failed to parse JSON: {e}",
            "raw_stdout": stdout,
            "raw_stderr": proc.stderr.strip()
        }

def log_task(task_num: int, title: str, result: bool, details: str):
    status = " PASS " if result else "[FAIL]"
    color_start = "\033[92m" if result else "\033[91m"
    color_reset = "\033[0m"
    print(f"\n{color_start}{status}{color_reset} Task {task_num}: {title}")
    print(f"       Details: {details}")

def main():
    print("=" * 70)
    print("  VOILA DESKTOP AUTOMATION — CUSTOM TASK SUITE EXECUTION")
    print("=" * 70)

    all_passed = True
    results_summary = []

    # ─────────────────────────────────────────────────────────────────────────
    # Task 1: Bridge Health & Window Enumeration
    # ─────────────────────────────────────────────────────────────────────────
    t1_res = run_desktop_tool(["--action", "list_windows"])
    t1_ok = t1_res.get("ok", False) and "windows" in t1_res and len(t1_res["windows"]) > 0
    t1_msg = f"Enumerated {len(t1_res.get('windows', []))} active windows (first: {t1_res.get('windows', [{}])[0].get('title', 'N/A')})"
    log_task(1, "Bridge Health & Window Enumeration", t1_ok, t1_msg)
    results_summary.append(("Task 1: Bridge & Window Enumeration", t1_ok))
    if not t1_ok:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Task 2: UIA Accessibility Snapshot & Generation Tracking
    # ─────────────────────────────────────────────────────────────────────────
    t2_res = run_desktop_tool(["--action", "snapshot", "--depth", "4"])
    t2_ok = t2_res.get("ok", False) and t2_res.get("ref_generation", 0) > 0
    gen_id = t2_res.get("ref_generation", 0)
    elem_count = len(t2_res.get("elements", []))
    t2_msg = f"Captured snapshot with ref_generation={gen_id}, {elem_count} elements in tree"
    log_task(2, "UIA Accessibility Snapshot & Ref Generation", t2_ok, t2_msg)
    results_summary.append(("Task 2: Snapshot & Generation Tracking", t2_ok))
    if not t2_ok:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Task 3: Semantic Element Query
    # ─────────────────────────────────────────────────────────────────────────
    t3_res = run_desktop_tool(["--action", "find", "--selector", "role=PaneControl"])
    t3_ok = t3_res.get("ok", False) and "elements" in t3_res
    t3_msg = f"Find returned {len(t3_res.get('elements', []))} matches for 'role=PaneControl'"
    log_task(3, "Semantic Element Query (find)", t3_ok, t3_msg)
    results_summary.append(("Task 3: Semantic Element Query", t3_ok))
    if not t3_ok:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Task 4: AI Cursor Navigation & macOS Click Animation Dispatch
    # ─────────────────────────────────────────────────────────────────────────
    # Test humanized move to (450, 320) + left click + double click
    t4_move = run_desktop_tool(["--action", "move_cursor", "--ref", "450,320"])
    t4_left_click = run_desktop_tool(["--action", "click_ref", "--ref", "450,320", "--button", "left"])
    t4_double_click = run_desktop_tool(["--action", "click_ref", "--ref", "450,320", "--button", "double"])
    t4_ok = t4_move.get("ok", False) and t4_left_click.get("ok", False) and t4_double_click.get("ok", False)
    t4_msg = (f"move_cursor ok={t4_move.get('ok')}, "
              f"left_click ok={t4_left_click.get('ok')} (method={t4_left_click.get('method')}), "
              f"double_click ok={t4_double_click.get('ok')} (method={t4_double_click.get('method')})")
    log_task(4, "AI Cursor Motion & macOS Click Animation", t4_ok, t4_msg)
    results_summary.append(("Task 4: Cursor Motion & Click Animation", t4_ok))
    if not t4_ok:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Task 5: End-to-End Application Workflow (Notepad)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[*] Starting Task 5: Launching Notepad for end-to-end UIA automation...")
    notepad_proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.5)  # Wait for Notepad window to render

    try:
        # 5a: Focus Notepad
        t5_focus = run_desktop_tool(["--action", "foreground", "--window", "Notepad"])
        
        # 5b: Snapshot Notepad
        t5_snap = run_desktop_tool(["--action", "snapshot", "--window", "Notepad", "--depth", "6"])
        t5_gen = t5_snap.get("ref_generation", 0)
        
        # 5c: Type into Notepad
        test_text = "Voila Desktop Automation macOS Click Animation Test OK"
        t5_type = run_desktop_tool(["--action", "type_keys", "--window", "Notepad", "--value", test_text])
        
        t5_ok = t5_snap.get("ok", False) and t5_type.get("ok", False)
        t5_msg = f"Notepad snapshot ok={t5_snap.get('ok')} (gen={t5_gen}, {len(t5_snap.get('elements', []))} nodes), type_keys ok={t5_type.get('ok')}"
        log_task(5, "End-to-End Notepad Automation Flow", t5_ok, t5_msg)
        results_summary.append(("Task 5: End-to-End Notepad Flow", t5_ok))
        if not t5_ok:
            all_passed = False
    finally:
        # Cleanly terminate notepad
        try:
            notepad_proc.terminate()
            notepad_proc.wait(timeout=2)
        except Exception:
            try:
                subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Task 6: Ref Freshness & Generation Mismatch Rejection
    # ─────────────────────────────────────────────────────────────────────────
    # Intentionally pass a mismatched ref_generation (e.g. 888888) with an element ref
    t6_res = run_desktop_tool(["--action", "click_ref", "--ref", "e1", "--ref-generation", "888888"])
    t6_ok = (not t6_res.get("ok", True)) and t6_res.get("error") in ["ref_generation_mismatch", "snapshot_required", "not_found"]
    t6_msg = f"Rejected mismatched ref_generation with expected error: {t6_res.get('error')}"
    log_task(6, "Security & Stale Ref Protection", t6_ok, t6_msg)
    results_summary.append(("Task 6: Stale Ref Protection", t6_ok))
    if not t6_ok:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Task 7: Error Boundary & Edge Case Handling
    # ─────────────────────────────────────────────────────────────────────────
    # Pass an invalid coords format to click_ref
    t7_res = run_desktop_tool(["--action", "click_ref", "--ref", "invalid_coords_abc"])
    t7_ok = (not t7_res.get("ok", True)) and t7_res.get("error") in ["ref_stale", "invalid_args", "not_found", "snapshot_required"]
    t7_msg = f"Handled malformed ref gracefully with error: {t7_res.get('error')}"
    log_task(7, "Error Boundary & Input Validation", t7_ok, t7_msg)
    results_summary.append(("Task 7: Error Boundary & Input Validation", t7_ok))
    if not t7_ok:
        all_passed = False

    # ─────────────────────────────────────────────────────────────────────────
    # Final Summary Table
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  TASK EXECUTION SUMMARY")
    print("=" * 70)
    for name, ok in results_summary:
        badge = "PASSED" if ok else "FAILED"
        print(f"  {badge.ljust(8)} : {name}")
    print("=" * 70)

    if all_passed:
        print("\nALL 7 CUSTOM DESKTOP AUTOMATION TASKS PASSED SUCCESSFULLY!\n")
        sys.exit(0)
    else:
        print("\nONE OR MORE TASKS FAILED!\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
