import sys
import os
import argparse
import json

# Setup import path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aegis.aegis_core import AegisMonitor

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--payload", default="")
    parser.add_argument("--window", default="")
    args = parser.parse_args()
    
    aegis_monitor = AegisMonitor(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    is_safe, reason = aegis_monitor.verify_action(args.action, args.payload, args.window)
    
    if not is_safe:
        print(f"SECURITY BLOCK: {reason}", file=sys.stderr)
        sys.exit(1)
        
    print("SAFE")
    sys.exit(0)

if __name__ == "__main__":
    main()
