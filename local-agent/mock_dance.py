import socket
import time
import math

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

print("Making Arjun (Port 19882) and Priya (Port 19883) dance...")

# Screen center approx
cx, cy = 960, 540
radius = 300

for i in range(100):
    angle = i * 0.1
    
    # Arjun circles clockwise
    ax = cx + radius * math.cos(angle)
    ay = cy + radius * math.sin(angle)
    
    # Priya circles counter-clockwise
    px = cx + radius * math.cos(-angle + math.pi)
    py = cy + radius * math.sin(-angle + math.pi)
    
    # Send UDP to Arjun's overlay
    sock.sendto(f"{int(ax)},{int(ay)}".encode('utf-8'), ('127.0.0.1', 19882))
    
    # Send UDP to Priya's overlay
    sock.sendto(f"{int(px)},{int(py)}".encode('utf-8'), ('127.0.0.1', 19883))
    
    time.sleep(0.05)

# Hide them
sock.sendto(b"HIDE", ('127.0.0.1', 19882))
sock.sendto(b"HIDE", ('127.0.0.1', 19883))
print("Dance complete!")
