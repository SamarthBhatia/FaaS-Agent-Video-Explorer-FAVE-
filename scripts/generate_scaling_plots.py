#!/usr/bin/env python3
"""
Generates the 4 plots the professor requested:
1. Throughput (JMeter) vs time
2. Total pods per function vs time
3. Response time per function vs time
4. Pod CPU utilization per function vs time

Usage:
    python3 scripts/generate_prof_plots.py --jtl experiments/jmeter/results_vm_consolidated.jtl \
        --pod-counts experiments/metrics/pod_counts_*.csv \
        --cpu-util experiments/metrics/cpu_util_*.csv \
        --output experiments/reports/prof
"""

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict
from datetime import datetime

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np
except ImportError:
    print("ERROR: matplotlib/numpy required. pip install matplotlib numpy")
    sys.exit(1)


def parse_jtl(path):
    """Parse JTL CSV, return list of dicts."""
    results = []
    with open(path) as f:
        for row in csv.DictReader(f):
            results.append({
                "timestamp": int(row.get("timeStamp", 0)),
                "elapsed": int(row.get("elapsed", 0)),
                "label": row.get("label", ""),
                "success": row.get("success", "").lower() == "true",
                "latency": int(row.get("Latency", 0)),
            })
    return results


def parse_pod_counts(paths):
    """Parse pod count CSVs."""
    rows = []
    for path in paths:
        with open(path) as f:
            for row in csv.DictReader(f):
                rows.append({
                    "timestamp": int(row["timestamp"]),
                    "function": row["function"],
                    "replicas": int(row["replicas"]),
                    "ready": int(row["ready"]),
                    "running": int(row["pods_running"]),
                })
    return rows


def parse_cpu_util(paths):
    """Parse CPU utilization CSVs."""
    rows = []
    for path in paths:
        with open(path) as f:
            for row in csv.DictReader(f):
                try:
                    rows.append({
                        "timestamp": int(row["timestamp"]),
                        "function": row["function"],
                        "cpu_m": int(row["cpu_millicores"]) if row["cpu_millicores"] else 0,
                        "mem_mib": int(row["memory_mib"]) if row["memory_mib"] else 0,
                    })
                except (ValueError, KeyError):
                    continue
    return rows


def plot_throughput(jtl_data, output_dir):
    """Plot 1: Throughput vs time from JMeter."""
    if not jtl_data:
        print("No JTL data for throughput plot")
        return

    timestamps = [r["timestamp"] / 1000.0 for r in jtl_data]
    t0 = min(timestamps)
    elapsed = [t - t0 for t in timestamps]

    # Bucket into 5-second windows
    max_t = max(elapsed) + 5
    buckets = np.arange(0, max_t, 5)
    counts = np.zeros(len(buckets))
    for t in elapsed:
        idx = int(t // 5)
        if idx < len(counts):
            counts[idx] += 1
    throughput = counts / 5.0  # requests per second

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(buckets, throughput, width=4.5, color="#0D9488", alpha=0.8, edgecolor="#028090")
    ax.set_xlabel("Time (seconds)", fontsize=12)
    ax.set_ylabel("Throughput (req/s)", fontsize=12)
    ax.set_title("JMeter Throughput vs Time", fontsize=14, fontweight="bold")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "1_throughput_vs_time.png"), dpi=150)
    plt.close(fig)
    print("  Plot 1: Throughput vs time saved")


def plot_pod_counts(pod_data, output_dir):
    """Plot 2: Total pods per function vs time."""
    if not pod_data:
        print("No pod count data")
        return

    # Group by function
    funcs = defaultdict(lambda: {"ts": [], "count": []})
    for row in pod_data:
        funcs[row["function"]]["ts"].append(row["timestamp"])
        funcs[row["function"]]["count"].append(row["running"])

    t0 = min(row["timestamp"] for row in pod_data)

    fig, ax = plt.subplots(figsize=(14, 7))
    colors = plt.cm.tab10(np.linspace(0, 1, len(funcs)))

    for (func, data), color in zip(sorted(funcs.items()), colors):
        elapsed = [(t - t0) for t in data["ts"]]
        ax.plot(elapsed, data["count"], label=func, linewidth=2, color=color, marker=".", markersize=3)

    ax.set_xlabel("Time (seconds)", fontsize=12)
    ax.set_ylabel("Running Pods", fontsize=12)
    ax.set_title("Total Pods per Function vs Time", fontsize=14, fontweight="bold")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "2_pods_per_function_vs_time.png"), dpi=150)
    plt.close(fig)
    print("  Plot 2: Pod counts vs time saved")


def plot_response_times(jtl_data, output_dir):
    """Plot 3: Response time vs time (from JMeter end-to-end)."""
    if not jtl_data:
        print("No JTL data for response time plot")
        return

    timestamps = [r["timestamp"] / 1000.0 for r in jtl_data]
    t0 = min(timestamps)
    elapsed = [t - t0 for t in timestamps]
    response_times = [r["elapsed"] / 1000.0 for r in jtl_data]
    success = [r["success"] for r in jtl_data]

    fig, ax = plt.subplots(figsize=(12, 6))

    # Color by success/failure
    succ_x = [e for e, s in zip(elapsed, success) if s]
    succ_y = [r for r, s in zip(response_times, success) if s]
    fail_x = [e for e, s in zip(elapsed, success) if not s]
    fail_y = [r for r, s in zip(response_times, success) if not s]

    ax.scatter(succ_x, succ_y, c="#0D9488", s=80, label="Success", zorder=3, edgecolors="#028090")
    if fail_x:
        ax.scatter(fail_x, fail_y, c="#EF4444", s=80, label="Failure", zorder=3, marker="x", linewidths=2)

    ax.set_xlabel("Time (seconds)", fontsize=12)
    ax.set_ylabel("Response Time (seconds)", fontsize=12)
    ax.set_title("Response Time vs Time", fontsize=14, fontweight="bold")
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "3_response_time_vs_time.png"), dpi=150)
    plt.close(fig)
    print("  Plot 3: Response time vs time saved")


def plot_cpu_utilization(cpu_data, output_dir):
    """Plot 4: CPU utilization per function vs time."""
    if not cpu_data:
        print("No CPU utilization data")
        return

    # Aggregate CPU per function per timestamp
    agg = defaultdict(lambda: defaultdict(int))
    for row in cpu_data:
        agg[row["timestamp"]][row["function"]] += row["cpu_m"]

    t0 = min(agg.keys())
    all_funcs = sorted(set(row["function"] for row in cpu_data))

    fig, ax = plt.subplots(figsize=(14, 7))
    colors = plt.cm.tab10(np.linspace(0, 1, len(all_funcs)))

    for func, color in zip(all_funcs, colors):
        times = sorted(agg.keys())
        elapsed = [(t - t0) for t in times]
        values = [agg[t].get(func, 0) for t in times]
        ax.plot(elapsed, values, label=func, linewidth=2, color=color)

    ax.set_xlabel("Time (seconds)", fontsize=12)
    ax.set_ylabel("CPU Usage (millicores)", fontsize=12)
    ax.set_title("CPU Utilization per Function vs Time", fontsize=14, fontweight="bold")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "4_cpu_utilization_vs_time.png"), dpi=150)
    plt.close(fig)
    print("  Plot 4: CPU utilization vs time saved")

    # Plot 4b: CPU utilization as percentage of request (100m per pod)
    CPU_REQUEST_M = 100  # each pod requests 100m CPU

    # Count pods per function per timestamp
    pod_counts_per_ts = defaultdict(lambda: defaultdict(int))
    for row in cpu_data:
        pod_counts_per_ts[row["timestamp"]][row["function"]] += 1

    fig, ax = plt.subplots(figsize=(14, 7))
    for func, color in zip(all_funcs, colors):
        times = sorted(agg.keys())
        elapsed = [(t - t0) for t in times]
        # Average utilization % = total CPU / (num_pods * request) * 100
        values = []
        for t in times:
            total_cpu = agg[t].get(func, 0)
            num_pods = pod_counts_per_ts[t].get(func, 1)
            avg_util = (total_cpu / (num_pods * CPU_REQUEST_M)) * 100
            values.append(avg_util)
        ax.plot(elapsed, values, label=func, linewidth=2, color=color)

    ax.axhline(y=60, color="red", linestyle="--", linewidth=1.5, alpha=0.7, label="HPA target (60%)")
    ax.set_xlabel("Time (seconds)", fontsize=12)
    ax.set_ylabel("Avg CPU Utilization (% of request)", fontsize=12)
    ax.set_title("CPU Utilization per Function vs Time (% of 100m request)", fontsize=14, fontweight="bold")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "4b_cpu_utilization_pct_vs_time.png"), dpi=150)
    plt.close(fig)
    print("  Plot 4b: CPU utilization (% of request) vs time saved")


def main():
    parser = argparse.ArgumentParser(description="Generate professor's requested plots")
    parser.add_argument("--jtl", required=True, help="JTL file (or consolidated)")
    parser.add_argument("--pod-counts", nargs="+", required=True, help="Pod count CSV files")
    parser.add_argument("--cpu-util", nargs="+", required=True, help="CPU utilization CSV files")
    parser.add_argument("--output", default="experiments/reports/prof", help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("Parsing data...")
    jtl_data = parse_jtl(args.jtl)
    pod_data = parse_pod_counts(args.pod_counts)
    cpu_data = parse_cpu_util(args.cpu_util)

    print(f"  JTL records: {len(jtl_data)}")
    print(f"  Pod count records: {len(pod_data)}")
    print(f"  CPU util records: {len(cpu_data)}")

    print("\nGenerating plots...")
    plot_throughput(jtl_data, args.output)
    plot_pod_counts(pod_data, args.output)
    plot_response_times(jtl_data, args.output)
    plot_cpu_utilization(cpu_data, args.output)

    print(f"\nAll plots saved to {args.output}/")


if __name__ == "__main__":
    main()
