import sys
import time
import json
import os
import math
import ctypes
import urllib.request

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32 = ctypes.windll.user32

def get_mouse_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def resample(points, n):
    """
    Equidistant arc-length polyline resampling.
    Guarantees exactly n points along the entire stroke without mutation or truncation.
    """
    if len(points) < 2:
        return [points[0]] * n if points else []
    
    # Calculate cumulative distance along path
    dists = [0.0]
    for i in range(1, len(points)):
        dists.append(dists[-1] + math.dist(points[i-1], points[i]))
        
    total_len = dists[-1]
    if total_len == 0:
        return [points[0]] * n
        
    interval = total_len / (n - 1)
    resampled = [points[0]]
    curr_idx = 0
    
    for j in range(1, n - 1):
        target_dist = j * interval
        while curr_idx < len(points) - 1 and dists[curr_idx + 1] < target_dist:
            curr_idx += 1
        
        seg_len = dists[curr_idx + 1] - dists[curr_idx]
        if seg_len > 0:
            t = (target_dist - dists[curr_idx]) / seg_len
            x = points[curr_idx][0] + t * (points[curr_idx + 1][0] - points[curr_idx][0])
            y = points[curr_idx][1] + t * (points[curr_idx + 1][1] - points[curr_idx][1])
            resampled.append((x, y))
        else:
            resampled.append(points[curr_idx])
            
    resampled.append(points[-1])
    return resampled

def normalize(points):
    """Normalizes points into [0, 1] unit square preserving aspect ratio."""
    if not points: return []
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    
    scale = max(max_x - min_x, max_y - min_y)
    if scale == 0: scale = 1
    
    return [((p[0] - min_x) / scale, (p[1] - min_y) / scale) for p in points]

def mirror_water(points):
    """Top-bottom inverted (Water image) -> Y axis inverted around 1.0."""
    return [(p[0], 1.0 - p[1]) for p in points]

def path_distance(p1, p2):
    """Mean Euclidean distance between paired points."""
    return sum(math.dist(a, b) for a, b in zip(p1, p2)) / len(p1)

def is_drawing():
    return (user32.GetAsyncKeyState(1) & 0x8000) != 0

def is_valid_stroke_size(pts, min_dim=70, min_pts=15):
    """Rejects small drags, text selections, and linear vertical/horizontal drags."""
    if len(pts) < min_pts:
        return False
    min_x = min(p[0] for p in pts)
    max_x = max(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    max_y = max(p[1] for p in pts)
    w = max_x - min_x
    h = max_y - min_y
    if w < min_dim or h < min_dim:
        return False
    aspect = w / h
    # An omega or inverted omega must be reasonably proportioned (not a vertical scroll or flat text select)
    if aspect < 0.50 or aspect > 1.85:
        return False
    return True

def is_topological_omega(pts):
    """
    Verifies that the normalized stroke exhibits the core structural topology of Omega (Ω):
    1. Both start and end (feet) are in the lower half (y >= 0.50).
    2. One foot is on the left side (x <= 0.40) and one is on the right side (x >= 0.60).
    3. The loop apex reaches the upper portion (y <= 0.35) near the middle of the stroke.
    4. Apex is centered horizontally (0.20 <= x <= 0.80).
    5. Vertical span is at least 0.40.
    """
    p_start = pts[0]
    p_end = pts[-1]
    if p_start[1] < 0.50 or p_end[1] < 0.50:
        return False
    left_ok = (p_start[0] <= 0.40 and p_end[0] >= 0.60) or (p_start[0] >= 0.60 and p_end[0] <= 0.40)
    if not left_ok:
        return False
    mid_pts = pts[12:52]
    min_y_mid = min(p[1] for p in mid_pts)
    min_pt = min(pts, key=lambda p: p[1])
    if min_y_mid > 0.35:
        return False
    if not (0.20 <= min_pt[0] <= 0.80):
        return False
    y_range = max(p[1] for p in pts) - min(p[1] for p in pts)
    if y_range < 0.40:
        return False
    return True

def is_topological_water_omega(pts):
    """
    Verifies that the normalized stroke exhibits the core structural topology of Water Omega (Ʊ):
    1. Both start and end (feet) are in the upper half (y <= 0.50).
    2. One foot is on the left side (x <= 0.40) and one is on the right side (x >= 0.60).
    3. The loop nadir reaches the lower portion (y >= 0.65) near the middle of the stroke.
    4. Nadir is centered horizontally (0.20 <= x <= 0.80).
    5. Vertical span is at least 0.40.
    """
    p_start = pts[0]
    p_end = pts[-1]
    if p_start[1] > 0.50 or p_end[1] > 0.50:
        return False
    left_ok = (p_start[0] <= 0.40 and p_end[0] >= 0.60) or (p_start[0] >= 0.60 and p_end[0] <= 0.40)
    if not left_ok:
        return False
    mid_pts = pts[12:52]
    max_y_mid = max(p[1] for p in mid_pts)
    max_pt = max(pts, key=lambda p: p[1])
    if max_y_mid < 0.65:
        return False
    if not (0.20 <= max_pt[0] <= 0.80):
        return False
    y_range = max(p[1] for p in pts) - min(p[1] for p in pts)
    if y_range < 0.40:
        return False
    return True

def classify_gesture(pts, templates, threshold=0.22):
    """
    Classifies a raw stroke into MATCH_OMEGA, MATCH_WATER_OMEGA, or NO_MATCH.
    Applies strict 3-tier validation:
    1. Raw size & aspect ratio checks.
    2. Normalized topological landmark invariants.
    3. Resampled Euclidean template distance + cross-disparity check.
    """
    if not is_valid_stroke_size(pts, min_dim=70, min_pts=15):
        return "NO_MATCH"

    norm_pts = normalize(resample(pts, 64))
    norm_pts_rev = list(reversed(norm_pts))

    dist_omega = min(path_distance(norm_pts, templates["omega"]), path_distance(norm_pts_rev, templates["omega"]))
    dist_water = min(path_distance(norm_pts, templates["water_omega"]), path_distance(norm_pts_rev, templates["water_omega"]))

    is_omega = is_topological_omega(norm_pts)
    is_water = is_topological_water_omega(norm_pts)

    if is_omega and dist_omega < threshold and dist_omega < (dist_water - 0.05):
        return "MATCH_OMEGA"
    elif is_water and dist_water < threshold and dist_water < (dist_omega - 0.05):
        return "MATCH_WATER_OMEGA"
    else:
        return "NO_MATCH"

def capture_path(duration=2.0):
    points = []
    last_p = None
    
    # Wait for the user to start drawing (left mouse button down)
    wait_start = time.time()
    while not is_drawing():
        if time.time() - wait_start > 5.0:
            return points
        time.sleep(0.01)
        
    start = time.time()
    while time.time() - start < duration and is_drawing():
        p = get_mouse_pos()
        if p != last_p:
            points.append(p)
            last_p = p
        time.sleep(0.01)
    return points

def main():
    if len(sys.argv) < 2:
        return
        
    action = sys.argv[1]
    data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_file = os.path.join(data_dir, "omega_template.json")
    
    if action == "train":
        print("Training... Please HOLD Left Mouse Button and draw an Omega.")
        pts = capture_path(5.0)
        if not is_valid_stroke_size(pts, min_dim=70, min_pts=15):
            print("Path too small, short, or invalid aspect ratio.")
            return
            
        norm_pts = normalize(resample(pts, 64))
        if not is_topological_omega(norm_pts):
            print("Gesture does not follow Omega shape (feet at bottom, apex at top).")
            return
            
        water_pts = mirror_water(norm_pts)
        with open(template_file, "w") as f:
            json.dump({"omega": norm_pts, "water_omega": water_pts}, f, indent=2)
        print("Template saved successfully.")
        
    elif action == "capture":
        if not os.path.exists(template_file):
            print("NOT_TRAINED")
            return
            
        with open(template_file, "r") as f:
            templates = json.load(f)
            
        print("Hold Left Mouse Button and draw gesture to capture...")
        pts = capture_path(5.0)
        result = classify_gesture(pts, templates, threshold=0.22)
        print(result)

    elif action == "daemon":
        if not os.path.exists(template_file):
            print("NOT_TRAINED")
            return
            
        with open(template_file, "r") as f:
            templates = json.load(f)
            
        print("Starting gesture daemon (HOLD Left Mouse Button to draw)...")
        
        pts = []
        drawing = False
        last_p = None
        
        while True:
            time.sleep(0.01)
            
            if is_drawing():
                if not drawing:
                    drawing = True
                    pts = []
                    last_p = get_mouse_pos()
                
                p = get_mouse_pos()
                if p != last_p:
                    pts.append(p)
                    last_p = p
            else:
                if drawing:
                    drawing = False
                    result = classify_gesture(pts, templates, threshold=0.22)
                    if result == "MATCH_OMEGA":
                        print("MATCH_OMEGA - Locking")
                        try:
                            req = urllib.request.Request('http://localhost:8088/surveillance/lock', method='POST')
                            urllib.request.urlopen(req, timeout=2)
                        except Exception:
                            pass
                    elif result == "MATCH_WATER_OMEGA":
                        print("MATCH_WATER_OMEGA - Unlocking")
                        try:
                            req = urllib.request.Request('http://localhost:8088/surveillance/unlock', method='POST')
                            urllib.request.urlopen(req, timeout=2)
                        except Exception:
                            pass
                    pts = []

if __name__ == "__main__":
    main()
