#!/usr/bin/env python3
"""
Sinusoidal non-homogeneous Poisson workload generator for FAVE pipeline.
Adapted from Samuele Pozzi's thesis Locust script.

Generates a sinusoidal RPS pattern over a configurable duration and sends
requests to the OpenFaaS orchestrator function.

Usage:
    python3 locust/locust_fave.py --gateway http://127.0.0.1:8080 \
        --duration 3600 --output experiments/locust
"""

import argparse
import csv
import itertools
import math
import os
import sys
import time

import numpy as np

# Patch stdlib for concurrent requests
from gevent import monkey
monkey.patch_all()

import gevent
from gevent import sleep
import requests


# === Sinusoidal workload parameters (matching Samuele's thesis) ===
BASE_RPS = 0
AMPLITUDE = 0.25
NOISE_STD = 0.01


def generate_rps_pattern(duration, seed):
    """Generate sinusoidal RPS pattern matching Samuele's thesis."""
    rng = np.random.RandomState(seed)
    t = np.linspace(0, 3 * np.pi, duration)
    rps = BASE_RPS + AMPLITUDE * np.sin(t) + rng.normal(0, NOISE_STD, duration)
    rps[rps < 0] = 0
    return rps


def generate_arrival_times(rps_pattern, duration, seed):
    """Non-homogeneous Poisson process via thinning method."""
    rng = np.random.RandomState(seed)
    max_rps = np.max(rps_pattern)
    if max_rps <= 0:
        return []

    # Generate homogeneous Poisson candidates at max rate
    expected = int(max_rps * duration * 2) + 100
    inter_arrivals = rng.exponential(1.0 / max_rps, expected)
    candidates = np.cumsum(inter_arrivals)
    candidates = candidates[candidates < duration]

    # Thin: accept with probability lambda(t) / max_rps
    accepted = []
    for t in candidates:
        idx = min(int(t), len(rps_pattern) - 1)
        if rng.random() < rps_pattern[idx] / max_rps:
            accepted.append(t)

    return accepted


def send_request(gateway_url, video_uri, results, req_id):
    """Send a single request to the orchestrator and record results."""
    url = f"{gateway_url}/function/orchestrator"
    payload = {"video_uri": video_uri, "profile": "locust-warm"}
    timestamp_ms = int(time.time() * 1000)
    start = time.perf_counter()

    try:
        resp = requests.post(url, json=payload, timeout=300)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        success = resp.status_code == 200
        # Check for pipeline failure in response body
        if success:
            try:
                body = resp.json()
                if body.get("status") != "ok":
                    success = False
            except Exception:
                pass
        results.append({
            "timeStamp": timestamp_ms,
            "elapsed": elapsed_ms,
            "label": "Process Video Request",
            "responseCode": resp.status_code,
            "responseMessage": "OK" if resp.status_code == 200 else str(resp.status_code),
            "threadName": f"Locust-{req_id}",
            "dataType": "text",
            "success": "true" if success else "false",
            "failureMessage": "" if success else "Pipeline did not return success status",
            "bytes": len(resp.content),
            "sentBytes": len(str(payload)),
            "grpThreads": 1,
            "allThreads": 1,
            "URL": url,
            "Latency": elapsed_ms,
            "IdleTime": 0,
            "Connect": 0,
        })
        status = "OK" if success else "FAIL"
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        results.append({
            "timeStamp": timestamp_ms,
            "elapsed": elapsed_ms,
            "label": "Process Video Request",
            "responseCode": 0,
            "responseMessage": str(e)[:50],
            "threadName": f"Locust-{req_id}",
            "dataType": "text",
            "success": "false",
            "failureMessage": str(e)[:100],
            "bytes": 0,
            "sentBytes": len(str(payload)),
            "grpThreads": 1,
            "allThreads": 1,
            "URL": url,
            "Latency": elapsed_ms,
            "IdleTime": 0,
            "Connect": 0,
        })
        status = "ERR"

    print(f"  [{req_id:3d}] {status} {elapsed_ms/1000:.1f}s  {video_uri.split('/')[-1]}")


def main():
    parser = argparse.ArgumentParser(description="FAVE Locust sinusoidal workload generator")
    parser.add_argument("--gateway", default="http://127.0.0.1:8080", help="OpenFaaS gateway URL")
    parser.add_argument("--duration", type=int, default=3600, help="Test duration in seconds (default: 3600)")
    parser.add_argument("--output", default="experiments/locust", help="Output directory")
    parser.add_argument("--videos-csv", default="datasets/jmeter_videos.csv", help="CSV with video URIs")
    parser.add_argument("--seed", type=int, default=22222121, help="Random seed (default: 22222121)")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    # Load videos
    videos = []
    with open(args.videos_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            videos.append(row["video_uri"])
    if not videos:
        print("ERROR: No videos found in", args.videos_csv)
        sys.exit(1)
    video_cycle = itertools.cycle(videos)
    print(f"Loaded {len(videos)} videos: {[v.split('/')[-1] for v in videos]}")

    # Generate workload
    print(f"\nGenerating sinusoidal RPS pattern (duration={args.duration}s, seed={args.seed})...")
    rps_pattern = generate_rps_pattern(args.duration, args.seed)
    print(f"  Max RPS: {np.max(rps_pattern):.4f}")
    print(f"  Mean RPS: {np.mean(rps_pattern):.4f}")

    # Save workload profile
    profile_path = os.path.join(args.output, "workloadProfile.csv")
    with open(profile_path, "w") as f:
        f.write("Time;RPS\n")
        for i, rps in enumerate(rps_pattern):
            f.write(f"{i};{rps}\n")
    print(f"  Saved workload profile: {profile_path}")

    # Generate arrival times
    arrival_times = generate_arrival_times(rps_pattern, args.duration, args.seed)
    print(f"\nWill send {len(arrival_times)} requests over {args.duration}s")
    if not arrival_times:
        print("ERROR: No requests generated")
        sys.exit(1)

    # Run experiment
    print(f"\nStarting experiment at {time.strftime('%H:%M:%S')}...")
    print(f"Gateway: {args.gateway}")
    print(f"Estimated completion: {time.strftime('%H:%M:%S', time.localtime(time.time() + args.duration))}")
    print()

    results = []
    start_time = time.time()

    # Schedule all requests via gevent
    greenlets = []
    for i, arrival_t in enumerate(arrival_times):
        video = next(video_cycle)
        g = gevent.spawn_later(
            arrival_t,
            send_request,
            args.gateway, video, results, i + 1
        )
        greenlets.append(g)

    # Wait for duration + extra time for last requests to complete
    sleep(args.duration + 60)
    gevent.joinall(greenlets, timeout=120)

    wall_time = time.time() - start_time
    print(f"\nExperiment complete in {wall_time:.0f}s")
    print(f"  Total requests: {len(results)}")
    successful = sum(1 for r in results if r["success"] == "true")
    print(f"  Successful: {successful}/{len(results)} ({100*successful/max(len(results),1):.0f}%)")

    # Save results in JTL format
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(start_time))
    jtl_path = os.path.join(args.output, f"results_locust_{timestamp}.jtl")
    fieldnames = [
        "timeStamp", "elapsed", "label", "responseCode", "responseMessage",
        "threadName", "dataType", "success", "failureMessage", "bytes",
        "sentBytes", "grpThreads", "allThreads", "URL", "Latency",
        "IdleTime", "Connect"
    ]
    # Sort by timestamp for clean output
    results.sort(key=lambda r: r["timeStamp"])
    with open(jtl_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"  JTL results: {jtl_path}")

    # Also save simple request_timestamps.csv (Samuele's format)
    ts_path = os.path.join(args.output, "request_timestamps.csv")
    with open(ts_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "ResponseTime"])
        for r in results:
            writer.writerow([r["timeStamp"] / 1000.0, r["elapsed"]])
    print(f"  Timestamps: {ts_path}")


if __name__ == "__main__":
    main()
