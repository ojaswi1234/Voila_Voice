import sys
import time
import json
import os
import math
import ctypes

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32 = ctypes.windll.user32

def get_mouse_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def resample(points, n):
    if len(points) < 2:
        return points
    # calculate path length
    total_len = 0
    for i in range(1, len(points)):
        total_len += math.dist(points[i-1], points[i])
    
    interval = total_len / (n - 1)
    resampled = [points[0]]
    current_dist = 0
    
    i = 1
    while i < len(points):
        d = math.dist(points[i-1], points[i])
        if current_dist + d >= interval:
            q = (interval - current_dist) / d
            qx = points[i-1][0] + q * (points[i][0] - points[i-1][0])
            qy = points[i-1][1] + q * (points[i][1] - points[i-1][1])
            new_pt = (qx, qy)
            resampled.append(new_pt)
            points.insert(i, new_pt)
            current_dist = 0
        else:
            current_dist += d
            i += 1
            
    # Float precision issues might result in slightly fewer points
    while len(resampled) < n:
        resampled.append(points[-1])
        
    return resampled[:n]

def normalize(points):
    if not points: return []
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    
    width = max_x - min_x
    height = max_y - min_y
    scale = max(width, height)
    if scale == 0: scale = 1
    
    normalized = []
    for p in points:
        nx = (p[0] - min_x) / scale
        ny = (p[1] - min_y) / scale
        normalized.append((nx, ny))
    return normalized

def mirror_water(points):
    # Top-bottom inverted (Water image) -> Y axis inverted
    # Since points are 0..1, inverted y is 1.0 - y
    return [(p[0], 1.0 - p[1]) for p in points]

def path_distance(p1, p2):
    # Simple Euclidean distance sum
    d = 0
    for a, b in zip(p1, p2):
        d += math.dist(a, b)
    return d / len(p1)

def capture_path(duration=2.0):
    start = time.time()
    points = []
    last_p = None
    while time.time() - start < duration:
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
        print("Training in 1 second... Please draw an Omega.")
        time.sleep(1)
        pts = capture_path(2.0)
        if len(pts) < 10:
            print("Path too short.")
            return
            
        norm_pts = normalize(resample(pts, 64))
        water_pts = mirror_water(norm_pts)
        
        with open(template_file, "w") as f:
            json.dump({"omega": norm_pts, "water_omega": water_pts}, f)
        print("Template saved.")
        
    elif action == "capture":
        if not os.path.exists(template_file):
            print("NOT_TRAINED")
            return
            
        with open(template_file, "r") as f:
            templates = json.load(f)
            
        time.sleep(0.5) # Short delay before capture
        pts = capture_path(2.0)
        
        if len(pts) < 10:
            print("NO_MATCH")
            return
            
        norm_pts = normalize(resample(pts, 64))
        
        dist_omega = path_distance(norm_pts, templates["omega"])
        dist_water = path_distance(norm_pts, templates["water_omega"])
        
        THRESHOLD = 0.25
        
        if dist_omega < THRESHOLD and dist_omega < dist_water:
            print("MATCH_OMEGA")
        elif dist_water < THRESHOLD:
            print("MATCH_WATER_OMEGA")
        else:
            print("NO_MATCH")

if __name__ == "__main__":
    main()
