import json
import statistics
import sys
from pathlib import Path

def analyze_results(filepath):
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return

    with open(path, 'r') as f:
        data = json.load(f)

    if not data:
        print(f"No data in {filepath}")
        return

    durations = [r['duration_ms'] for r in data if r['status'] == 'success']
    errors = len([r for r in data if r['status'] != 'success'])
    total = len(data)

    print(f"--- {path.name} ---")
    print(f"Total Requests: {total}")
    print(f"Success Rate:   {((total - errors) / total) * 100:.1f}%")
    
    if durations:
        print(f"Latency (ms):")
        print(f"  Min: {min(durations)}")
        print(f"  P50: {statistics.median(durations):.0f}")
        print(f"  P90: {statistics.quantiles(durations, n=10)[8]:.0f}")
        print(f"  Max: {max(durations)}")
    else:
        print("No successful requests to analyze latency.")
    print("")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <results_dir>")
        sys.exit(1)
    
    results_dir = Path(sys.argv[1])
    for f in sorted(results_dir.glob("results_*.json")):
        analyze_results(f)
