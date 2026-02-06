#!/usr/bin/env python3
"""
MinIO Storage Backend Benchmark Script

Compares latency between disk-backed and RAM-disk MinIO configurations.
Measures: upload latency, download latency, and full pipeline latency.

Usage:
    python3 scripts/benchmark_minio.py --mode disk --iterations 10
    python3 scripts/benchmark_minio.py --mode ramdisk --iterations 10
    python3 scripts/benchmark_minio.py --compare  # Compare saved results
"""

import argparse
import io
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import boto3
import matplotlib.pyplot as plt
from botocore.client import Config

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "faveadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "favesecret")
BUCKET_NAME = "fave-benchmark"
RESULTS_DIR = Path("experiments/benchmark")


def get_s3_client():
    """Create MinIO S3 client."""
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket(client) -> None:
    """Ensure benchmark bucket exists."""
    try:
        client.head_bucket(Bucket=BUCKET_NAME)
    except Exception:
        client.create_bucket(Bucket=BUCKET_NAME)
        print(f"Created bucket: {BUCKET_NAME}")


def generate_test_data(size_mb: int = 10) -> bytes:
    """Generate random test data of specified size."""
    return os.urandom(size_mb * 1024 * 1024)


def benchmark_upload(client, data: bytes, key: str) -> float:
    """Benchmark upload latency in milliseconds."""
    buf = io.BytesIO(data)
    start = time.perf_counter()
    client.upload_fileobj(buf, BUCKET_NAME, key)
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_download(client, key: str) -> float:
    """Benchmark download latency in milliseconds."""
    buf = io.BytesIO()
    start = time.perf_counter()
    client.download_fileobj(BUCKET_NAME, key, buf)
    end = time.perf_counter()
    return (end - start) * 1000


def benchmark_roundtrip(client, data: bytes, key: str) -> Dict[str, float]:
    """Benchmark full upload + download roundtrip."""
    upload_ms = benchmark_upload(client, data, key)
    download_ms = benchmark_download(client, key)
    return {
        "upload_ms": upload_ms,
        "download_ms": download_ms,
        "roundtrip_ms": upload_ms + download_ms,
    }


def run_benchmark(
    mode: str,
    iterations: int = 10,
    file_sizes_mb: List[int] = [1, 5, 10, 50],
) -> Dict:
    """Run complete benchmark suite."""
    print(f"\n{'='*60}")
    print(f"MinIO Benchmark - Mode: {mode.upper()}")
    print(f"Endpoint: {MINIO_ENDPOINT}")
    print(f"Iterations: {iterations}")
    print(f"File sizes: {file_sizes_mb} MB")
    print(f"{'='*60}\n")

    client = get_s3_client()
    ensure_bucket(client)

    results = {
        "mode": mode,
        "endpoint": MINIO_ENDPOINT,
        "timestamp": datetime.now().isoformat(),
        "iterations": iterations,
        "file_sizes_mb": file_sizes_mb,
        "benchmarks": {},
    }

    for size_mb in file_sizes_mb:
        print(f"\nBenchmarking {size_mb} MB files...")
        data = generate_test_data(size_mb)

        upload_times = []
        download_times = []
        roundtrip_times = []

        for i in range(iterations):
            key = f"benchmark/{mode}/{size_mb}mb/test_{i}.bin"
            result = benchmark_roundtrip(client, data, key)
            upload_times.append(result["upload_ms"])
            download_times.append(result["download_ms"])
            roundtrip_times.append(result["roundtrip_ms"])

            # Cleanup
            try:
                client.delete_object(Bucket=BUCKET_NAME, Key=key)
            except Exception:
                pass

            print(f"  Iteration {i+1}/{iterations}: "
                  f"upload={result['upload_ms']:.1f}ms, "
                  f"download={result['download_ms']:.1f}ms")

        # Calculate statistics
        results["benchmarks"][f"{size_mb}mb"] = {
            "upload": {
                "mean_ms": statistics.mean(upload_times),
                "median_ms": statistics.median(upload_times),
                "stdev_ms": statistics.stdev(upload_times) if len(upload_times) > 1 else 0,
                "min_ms": min(upload_times),
                "max_ms": max(upload_times),
                "all_ms": upload_times,
            },
            "download": {
                "mean_ms": statistics.mean(download_times),
                "median_ms": statistics.median(download_times),
                "stdev_ms": statistics.stdev(download_times) if len(download_times) > 1 else 0,
                "min_ms": min(download_times),
                "max_ms": max(download_times),
                "all_ms": download_times,
            },
            "roundtrip": {
                "mean_ms": statistics.mean(roundtrip_times),
                "median_ms": statistics.median(roundtrip_times),
                "stdev_ms": statistics.stdev(roundtrip_times) if len(roundtrip_times) > 1 else 0,
                "min_ms": min(roundtrip_times),
                "max_ms": max(roundtrip_times),
                "all_ms": roundtrip_times,
            },
        }

        print(f"  Summary: upload={statistics.mean(upload_times):.1f}ms (mean), "
              f"download={statistics.mean(download_times):.1f}ms (mean)")

    return results


def save_results(results: Dict, mode: str) -> Path:
    """Save benchmark results to JSON file."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    filepath = RESULTS_DIR / f"benchmark_{mode}_{timestamp}.json"
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {filepath}")
    return filepath


def load_latest_results(mode: str) -> Optional[Dict]:
    """Load most recent results for a given mode."""
    if not RESULTS_DIR.exists():
        return None
    files = sorted(RESULTS_DIR.glob(f"benchmark_{mode}_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        return json.load(f)


def compare_results(disk_results: Dict, ramdisk_results: Dict) -> None:
    """Compare disk vs RAM-disk results and generate report."""
    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON: Disk vs RAM-disk MinIO")
    print("=" * 70)

    # Print comparison table
    print(f"\n{'File Size':<12} {'Metric':<12} {'Disk (ms)':<15} {'RAM-disk (ms)':<15} {'Speedup':<10}")
    print("-" * 70)

    comparison_data = []

    for size_key in disk_results["benchmarks"]:
        disk_bench = disk_results["benchmarks"][size_key]
        ramdisk_bench = ramdisk_results["benchmarks"].get(size_key, {})

        if not ramdisk_bench:
            continue

        for metric in ["upload", "download", "roundtrip"]:
            disk_mean = disk_bench[metric]["mean_ms"]
            ramdisk_mean = ramdisk_bench[metric]["mean_ms"]
            speedup = disk_mean / ramdisk_mean if ramdisk_mean > 0 else 0

            print(f"{size_key:<12} {metric:<12} {disk_mean:<15.2f} {ramdisk_mean:<15.2f} {speedup:<10.2f}x")

            comparison_data.append({
                "size": size_key,
                "metric": metric,
                "disk_ms": disk_mean,
                "ramdisk_ms": ramdisk_mean,
                "speedup": speedup,
            })

    # Generate comparison chart
    generate_comparison_chart(disk_results, ramdisk_results)

    # Save comparison summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "disk_results_file": disk_results.get("timestamp"),
        "ramdisk_results_file": ramdisk_results.get("timestamp"),
        "comparison": comparison_data,
    }
    summary_path = RESULTS_DIR / "comparison_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nComparison summary saved to: {summary_path}")


def generate_comparison_chart(disk_results: Dict, ramdisk_results: Dict) -> None:
    """Generate comparison bar chart."""
    sizes = list(disk_results["benchmarks"].keys())
    metrics = ["upload", "download", "roundtrip"]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for idx, metric in enumerate(metrics):
        disk_values = [disk_results["benchmarks"][s][metric]["mean_ms"] for s in sizes]
        ramdisk_values = [ramdisk_results["benchmarks"][s][metric]["mean_ms"] for s in sizes]

        x = range(len(sizes))
        width = 0.35

        axes[idx].bar([i - width/2 for i in x], disk_values, width, label="Disk", color="steelblue")
        axes[idx].bar([i + width/2 for i in x], ramdisk_values, width, label="RAM-disk", color="coral")

        axes[idx].set_xlabel("File Size")
        axes[idx].set_ylabel("Latency (ms)")
        axes[idx].set_title(f"{metric.capitalize()} Latency")
        axes[idx].set_xticks(x)
        axes[idx].set_xticklabels(sizes)
        axes[idx].legend()
        axes[idx].grid(axis="y", alpha=0.3)

    plt.suptitle("MinIO Storage Backend Comparison: Disk vs RAM-disk", fontsize=14, fontweight="bold")
    plt.tight_layout()

    chart_path = RESULTS_DIR / "benchmark_comparison.png"
    plt.savefig(chart_path, dpi=150, bbox_inches="tight")
    print(f"\nComparison chart saved to: {chart_path}")
    plt.close()


def print_summary(results: Dict) -> None:
    """Print benchmark summary table."""
    print("\n" + "=" * 60)
    print(f"BENCHMARK SUMMARY - {results['mode'].upper()}")
    print("=" * 60)
    print(f"\n{'File Size':<12} {'Upload (ms)':<15} {'Download (ms)':<15} {'Roundtrip (ms)':<15}")
    print("-" * 60)

    for size_key, bench in results["benchmarks"].items():
        upload = bench["upload"]["mean_ms"]
        download = bench["download"]["mean_ms"]
        roundtrip = bench["roundtrip"]["mean_ms"]
        print(f"{size_key:<12} {upload:<15.2f} {download:<15.2f} {roundtrip:<15.2f}")


def main():
    parser = argparse.ArgumentParser(description="MinIO Storage Backend Benchmark")
    parser.add_argument(
        "--mode",
        choices=["disk", "ramdisk"],
        help="Storage backend mode to benchmark",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Number of iterations per file size (default: 10)",
    )
    parser.add_argument(
        "--sizes",
        type=int,
        nargs="+",
        default=[1, 5, 10],
        help="File sizes in MB to test (default: 1 5 10)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare latest disk and ramdisk results",
    )

    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.compare:
        disk_results = load_latest_results("disk")
        ramdisk_results = load_latest_results("ramdisk")

        if not disk_results:
            print("ERROR: No disk benchmark results found. Run with --mode disk first.")
            return 1
        if not ramdisk_results:
            print("ERROR: No ramdisk benchmark results found. Run with --mode ramdisk first.")
            return 1

        compare_results(disk_results, ramdisk_results)
        return 0

    if not args.mode:
        parser.error("--mode is required unless --compare is specified")

    results = run_benchmark(
        mode=args.mode,
        iterations=args.iterations,
        file_sizes_mb=args.sizes,
    )

    print_summary(results)
    save_results(results, args.mode)

    return 0


if __name__ == "__main__":
    exit(main())
