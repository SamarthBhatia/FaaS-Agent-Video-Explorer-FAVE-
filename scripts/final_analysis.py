import json
import statistics
import sys
from pathlib import Path

def analyze_results(filepath):
    path = Path(filepath)
    if not path.exists():
        return None

    with open(path, 'r') as f:
        data = json.load(f)

    if not data:
        return None

    total = len(data)
    gateway_failures = 0
    app_errors = 0
    true_successes = []

    for r in data:
        if r['status'] != 'success':
            gateway_failures += 1
        else:
            resp = r.get('response', {})
            if resp.get('status') == 'error':
                app_errors += 1
            else:
                true_successes.append(r)

    durations = [r['duration_ms'] for r in true_successes]
    
    # Extract cost units if available in the response result
    costs = []
    for r in true_successes:
        # result metrics are often nested in response['result']['metrics']
        # but let's try to find them
        res = r.get('response', {}).get('result', {})
        if isinstance(res, dict):
            # linear stages
            for stage in res.get('linear', []):
                m = stage.get('metrics', {})
                if 'cost_unit' in m:
                    costs.append(m['cost_unit'])
            # clips
            for clip in res.get('clips', []):
                for stage in clip.get('stages', []):
                    m = stage.get('metrics', {})
                    if 'cost_unit' in m:
                        costs.append(m['cost_unit'])

    stats = {
        "name": path.name,
        "total": total,
        "gateway_fail": gateway_failures,
        "app_error": app_errors,
        "success_rate": (len(true_successes) / total) * 100 if total > 0 else 0,
        "p50": statistics.median(durations) if len(durations) > 0 else 0,
        "p90": statistics.quantiles(durations, n=10)[8] if len(durations) > 1 else (durations[0] if len(durations) == 1 else 0),
        "avg_cost": sum(costs) / len(true_successes) if len(true_successes) > 0 and len(costs) > 0 else 0
    }
    return stats

if __name__ == "__main__":
    results_dir = Path("experiments")
    all_stats = []
    for f in sorted(results_dir.glob("results_*.json")):
        s = analyze_results(f)
        if s:
            all_stats.append(s)

    print(f"{'Experiment':<40} | {'Succ%':>6} | {'P50(ms)':>8} | {'P90(ms)':>8} | {'Cost':>8}")
    print("-" * 80)
    for s in all_stats:
        print(f"{s['name'][:40]:<40} | {s['success_rate']:>5.1f}% | {s['p50']:>8.0f} | {s['p90']:>8.0f} | {s['avg_cost']:>8.2f}")
