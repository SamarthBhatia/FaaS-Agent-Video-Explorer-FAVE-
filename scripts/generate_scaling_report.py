#!/usr/bin/env python3
"""
FAVE Scaling Report Generator

Reads JTL results from experiments/jmeter/, groups by thread count and mode,
and generates comparison plots and a summary table.

Usage:
    python3 scripts/generate_scaling_report.py
    python3 scripts/generate_scaling_report.py --output-dir experiments/reports
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    print("ERROR: matplotlib is required. Install with: pip install matplotlib")
    sys.exit(1)


def parse_jtl(jtl_path):
    """Parse a JTL CSV file and return list of result dicts."""
    results = []
    with open(jtl_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append({
                "timestamp": int(row.get("timeStamp", 0)),
                "duration_ms": int(row.get("elapsed", 0)),
                "success": row.get("success", "").lower() == "true",
                "latency_ms": int(row.get("Latency", 0)),
                "connect_ms": int(row.get("Connect", 0)),
                "bytes": int(row.get("bytes", 0)),
                "label": row.get("label", ""),
            })
    return results


def extract_metadata(filename):
    """Extract mode and thread count from filename like results_warm_5t_20260311.jtl"""
    match = re.match(r"results_(\w+)_(\d+)t_", filename)
    if match:
        return match.group(1), int(match.group(2))
    return None, None


def compute_stats(results):
    """Compute summary statistics from a list of result dicts."""
    if not results:
        return {}

    durations = [r["duration_ms"] for r in results]
    latencies = [r["latency_ms"] for r in results]
    successes = sum(1 for r in results if r["success"])
    total = len(results)

    timestamps = [r["timestamp"] for r in results]
    elapsed_sec = (max(timestamps) - min(timestamps)) / 1000.0 if len(timestamps) > 1 else 1.0
    throughput = total / elapsed_sec if elapsed_sec > 0 else 0

    return {
        "total": total,
        "success_rate": successes / total * 100 if total else 0,
        "avg_duration": np.mean(durations),
        "median_duration": np.median(durations),
        "p95_duration": np.percentile(durations, 95),
        "p99_duration": np.percentile(durations, 99),
        "avg_latency": np.mean(latencies),
        "p95_latency": np.percentile(latencies, 95),
        "p99_latency": np.percentile(latencies, 99),
        "throughput_rps": throughput,
        "min_duration": np.min(durations),
        "max_duration": np.max(durations),
    }


def generate_plots(grouped_stats, output_dir):
    """Generate comparison plots from grouped statistics."""
    output_dir.mkdir(parents=True, exist_ok=True)

    modes = sorted(grouped_stats.keys())
    colors = {"warm": "#2196F3", "cold": "#FF5722"}

    # Collect all thread counts across modes
    all_threads = sorted({tc for mode_data in grouped_stats.values() for tc in mode_data})

    # --- Plot 1: Avg Response Time vs Thread Count ---
    fig, ax = plt.subplots(figsize=(10, 6))
    for mode in modes:
        threads = sorted(grouped_stats[mode].keys())
        avgs = [grouped_stats[mode][t]["avg_duration"] for t in threads]
        ax.plot(threads, avgs, "o-", label=f"{mode}", color=colors.get(mode, None), linewidth=2, markersize=8)
    ax.set_xlabel("Thread Count", fontsize=12)
    ax.set_ylabel("Avg Response Time (ms)", fontsize=12)
    ax.set_title("Average Response Time vs Concurrency", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(all_threads)
    fig.tight_layout()
    fig.savefig(output_dir / "avg_response_time.png", dpi=150)
    plt.close(fig)

    # --- Plot 2: Throughput vs Thread Count ---
    fig, ax = plt.subplots(figsize=(10, 6))
    for mode in modes:
        threads = sorted(grouped_stats[mode].keys())
        tps = [grouped_stats[mode][t]["throughput_rps"] for t in threads]
        ax.plot(threads, tps, "o-", label=f"{mode}", color=colors.get(mode, None), linewidth=2, markersize=8)
    ax.set_xlabel("Thread Count", fontsize=12)
    ax.set_ylabel("Throughput (req/s)", fontsize=12)
    ax.set_title("Throughput vs Concurrency", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(all_threads)
    fig.tight_layout()
    fig.savefig(output_dir / "throughput.png", dpi=150)
    plt.close(fig)

    # --- Plot 3: P95/P99 Latency vs Thread Count ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for i, percentile in enumerate(["p95_duration", "p99_duration"]):
        ax = axes[i]
        label = percentile.replace("_duration", "").upper()
        for mode in modes:
            threads = sorted(grouped_stats[mode].keys())
            vals = [grouped_stats[mode][t][percentile] for t in threads]
            ax.plot(threads, vals, "o-", label=f"{mode}", color=colors.get(mode, None), linewidth=2, markersize=8)
        ax.set_xlabel("Thread Count", fontsize=12)
        ax.set_ylabel(f"{label} Latency (ms)", fontsize=12)
        ax.set_title(f"{label} Latency vs Concurrency", fontsize=14)
        ax.legend(fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_xticks(all_threads)
    fig.tight_layout()
    fig.savefig(output_dir / "p95_p99_latency.png", dpi=150)
    plt.close(fig)

    # --- Plot 4: Success Rate vs Thread Count ---
    fig, ax = plt.subplots(figsize=(10, 6))
    for mode in modes:
        threads = sorted(grouped_stats[mode].keys())
        rates = [grouped_stats[mode][t]["success_rate"] for t in threads]
        ax.plot(threads, rates, "o-", label=f"{mode}", color=colors.get(mode, None), linewidth=2, markersize=8)
    ax.set_xlabel("Thread Count", fontsize=12)
    ax.set_ylabel("Success Rate (%)", fontsize=12)
    ax.set_title("Success Rate vs Concurrency", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(all_threads)
    ax.set_ylim(0, 105)
    fig.tight_layout()
    fig.savefig(output_dir / "success_rate.png", dpi=150)
    plt.close(fig)

    print(f"Plots saved to {output_dir}/")


def print_summary_table(grouped_stats):
    """Print a formatted summary table."""
    print("\n" + "=" * 100)
    print("FAVE Scaling Experiment — Summary")
    print("=" * 100)
    print(f"{'Mode':<8} {'Threads':>8} {'Total':>6} {'Success%':>9} {'Avg(ms)':>9} "
          f"{'P95(ms)':>9} {'P99(ms)':>9} {'Throughput':>12}")
    print("-" * 100)

    for mode in sorted(grouped_stats.keys()):
        for threads in sorted(grouped_stats[mode].keys()):
            s = grouped_stats[mode][threads]
            print(f"{mode:<8} {threads:>8} {s['total']:>6} {s['success_rate']:>8.1f}% "
                  f"{s['avg_duration']:>9.0f} {s['p95_duration']:>9.0f} {s['p99_duration']:>9.0f} "
                  f"{s['throughput_rps']:>10.2f}/s")

    print("=" * 100)


def main():
    parser = argparse.ArgumentParser(description="FAVE Scaling Report Generator")
    parser.add_argument("--results-dir", default="experiments/jmeter",
                        help="Directory containing JTL result files")
    parser.add_argument("--output-dir", default="experiments/reports",
                        help="Output directory for plots and reports")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)

    if not results_dir.exists():
        print(f"ERROR: Results directory not found: {results_dir}")
        sys.exit(1)

    jtl_files = sorted(results_dir.glob("*.jtl"))
    if not jtl_files:
        print(f"ERROR: No JTL files found in {results_dir}")
        sys.exit(1)

    print(f"Found {len(jtl_files)} JTL files in {results_dir}")

    # Group results by mode and thread count
    # Use the latest file for each (mode, threads) combination
    latest_files = {}
    for jtl in jtl_files:
        mode, threads = extract_metadata(jtl.name)
        if mode and threads:
            key = (mode, threads)
            # Keep latest (files are sorted, last wins)
            latest_files[key] = jtl

    # Parse and compute stats
    grouped_stats = defaultdict(dict)
    for (mode, threads), jtl_path in sorted(latest_files.items()):
        print(f"  Processing: {jtl_path.name} ({mode}, {threads}t)")
        results = parse_jtl(jtl_path)
        if results:
            stats = compute_stats(results)
            grouped_stats[mode][threads] = stats

    if not grouped_stats:
        print("ERROR: No valid results to analyze")
        sys.exit(1)

    print_summary_table(grouped_stats)
    generate_plots(grouped_stats, output_dir)

    # Save summary as CSV
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "scaling_summary.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["mode", "threads", "total_requests", "success_rate",
                         "avg_duration_ms", "median_duration_ms", "p95_duration_ms",
                         "p99_duration_ms", "throughput_rps"])
        for mode in sorted(grouped_stats.keys()):
            for threads in sorted(grouped_stats[mode].keys()):
                s = grouped_stats[mode][threads]
                writer.writerow([mode, threads, s["total"], f"{s['success_rate']:.1f}",
                                 f"{s['avg_duration']:.0f}", f"{s['median_duration']:.0f}",
                                 f"{s['p95_duration']:.0f}", f"{s['p99_duration']:.0f}",
                                 f"{s['throughput_rps']:.2f}"])

    print(f"\nCSV summary: {csv_path}")
    print("Done!")


if __name__ == "__main__":
    main()
