import json
from pathlib import Path

def analyze_failures(filepath):
    path = Path(filepath)
    if not path.exists(): return
    with open(path, 'r') as f:
        data = json.load(f)
    
    gw_fail = 0
    app_error = 0
    app_error_msgs = {}
    success = 0

    for r in data:
        if r['status'] != 'success':
            gw_fail += 1
        else:
            resp = r.get('response', {})
            if resp.get('status') == 'error':
                app_error += 1
                msg = str(resp.get('message', 'unknown'))[:50]
                app_error_msgs[msg] = app_error_msgs.get(msg, 0) + 1
            else:
                success += 1
    
    print(f"--- {path.name} ---")
    print(f"  Success:  {success}")
    print(f"  GW Fail: {gw_fail}")
    print(f"  App Err: {app_error}")
    for msg, count in app_error_msgs.items():
        print(f"    - {msg}: {count}")

if __name__ == "__main__":
    results_dir = Path("experiments")
    # Only analyze the main experiment runs
    for pattern in ["warm-steady", "warm-burst", "cold-steady", "cold-burst"]:
        for f in results_dir.glob(f"results_*{pattern}*.json"):
            analyze_failures(f)
