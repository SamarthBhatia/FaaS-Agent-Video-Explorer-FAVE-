#!/usr/bin/env python3
"""
FAVE Experiment Analysis Script

Analyzes experiment results and generates:
1. Summary statistics table
2. Success rate and latency bar charts
3. Cost-vs-latency scatter plots (cold vs warm regimes)
4. Regime comparison boxplots
5. CSV export of regime statistics

Usage:
    python3 scripts/final_analysis.py
    python3 scripts/final_analysis.py --experiments-dir experiments
"""

import argparse
import csv
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    filename: str
    request_id: str
    duration_ms: float
    total_cost: float
    regime: str  # 'cold', 'warm', 'default'
    profile: str
    success: bool
    cold_start_count: int
    total_stages: int


def classify_regime(filename: str, profile: str) -> str:
    """
    Classify experiment regime from filename and profile.

    Returns: 'cold', 'warm', or 'default'
    """
    filename_lower = filename.lower()
    profile_lower = profile.lower() if profile else ''

    # Check for cold indicators
    if 'cold' in filename_lower or 'cold' in profile_lower:
        return 'cold'

    # Check for warm indicators
    if 'warm' in filename_lower or 'warm' in profile_lower:
        return 'warm'

    # Check for burst (often indicates cold start scenario)
    if 'burst' in filename_lower:
        return 'cold'

    return 'default'


def extract_full_cost(response: Dict) -> Tuple[float, int, int]:
    """
    Extract total cost from all stages (linear + clips).

    Returns: (total_cost, cold_start_count, total_stages)
    """
    total_cost = 0.0
    cold_start_count = 0
    total_stages = 0

    result = response.get('result', {})
    if not isinstance(result, dict):
        return (0.0, 0, 0)

    # Linear stages
    for stage in result.get('linear', []):
        metrics = stage.get('metrics', {})
        if 'cost_unit' in metrics:
            total_cost += metrics['cost_unit']
            total_stages += 1
            if metrics.get('cold_start', False):
                cold_start_count += 1

    # Clip stages (nested)
    for clip in result.get('clips', []):
        for stage in clip.get('stages', []):
            metrics = stage.get('metrics', {})
            if 'cost_unit' in metrics:
                total_cost += metrics['cost_unit']
                total_stages += 1
                if metrics.get('cold_start', False):
                    cold_start_count += 1

    return (total_cost, cold_start_count, total_stages)


def parse_experiment_file(filepath: Path) -> List[RequestMetrics]:
    """Parse experiment JSON file and extract per-request metrics."""
    if not filepath.exists():
        return []

    with open(filepath, 'r') as f:
        data = json.load(f)

    if not data:
        return []

    filename = filepath.name
    metrics_list = []

    for record in data:
        # Skip failed requests
        if record.get('status') != 'success':
            continue

        response = record.get('response', {})
        if response.get('status') == 'error':
            continue

        profile = record.get('profile', 'default')
        regime = classify_regime(filename, profile)

        total_cost, cold_count, stage_count = extract_full_cost(response)

        metrics = RequestMetrics(
            filename=filename,
            request_id=response.get('request_id', 'unknown'),
            duration_ms=record.get('duration_ms', 0),
            total_cost=total_cost,
            regime=regime,
            profile=profile,
            success=True,
            cold_start_count=cold_count,
            total_stages=stage_count,
        )
        metrics_list.append(metrics)

    return metrics_list


def analyze_results(filepath: Path) -> Optional[Dict]:
    """Analyze a single experiment file (legacy function for compatibility)."""
    if not filepath.exists():
        return None

    with open(filepath, 'r') as f:
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

    # Extract full cost per request
    costs = []
    for r in true_successes:
        total_cost, _, _ = extract_full_cost(r.get('response', {}))
        if total_cost > 0:
            costs.append(total_cost)

    # Determine regime from filename
    regime = classify_regime(filepath.name, data[0].get('profile', '') if data else '')

    stats = {
        "name": filepath.name,
        "total": total,
        "gateway_fail": gateway_failures,
        "app_error": app_errors,
        "success_rate": (len(true_successes) / total) * 100 if total > 0 else 0,
        "p50": statistics.median(durations) if len(durations) > 0 else 0,
        "p90": statistics.quantiles(durations, n=10)[8] if len(durations) > 1 else (durations[0] if len(durations) == 1 else 0),
        "avg_cost": statistics.mean(costs) if costs else 0,
        "total_cost": sum(costs),
        "regime": regime,
    }
    return stats


def plot_results(stats_list: List[Dict], output_path: Path) -> None:
    """Generate basic bar charts (legacy function)."""
    if not stats_list:
        print("No stats to plot.")
        return

    names = [s['name'][:30] + '...' if len(s['name']) > 30 else s['name'] for s in stats_list]
    success_rates = [s['success_rate'] for s in stats_list]
    p50_latencies = [s['p50'] for s in stats_list]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    fig.suptitle('Experiment Results Summary', fontsize=16, fontweight='bold')

    # Success Rate Plot
    colors = ['coral' if s.get('regime') == 'cold' else 'steelblue' if s.get('regime') == 'warm' else 'gray'
              for s in stats_list]
    ax1.barh(names, success_rates, color=colors)
    ax1.set_xlabel('Success Rate (%)')
    ax1.set_title('Success Rate per Experiment (Blue=Warm, Orange=Cold, Gray=Default)')
    ax1.set_xlim(0, 105)
    for index, value in enumerate(success_rates):
        ax1.text(value + 1, index, f"{value:.1f}%", va='center')

    # P50 Latency Plot
    ax2.barh(names, p50_latencies, color=colors)
    ax2.set_xlabel('P50 Latency (ms)')
    ax2.set_title('P50 Latency per Experiment')
    for index, value in enumerate(p50_latencies):
        ax2.text(value + 50, index, f"{value:.0f}ms", va='center')

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Summary plot saved to {output_path}")
    plt.close()


def plot_cost_vs_latency_scatter(all_metrics: List[RequestMetrics], output_path: Path) -> None:
    """
    Generate cost vs latency scatter plot with regime coloring.
    X-axis: Latency (seconds)
    Y-axis: Cost (units)
    Color: Regime (cold=red, warm=blue, default=gray)
    """
    if not all_metrics:
        print("No metrics for scatter plot.")
        return

    # Separate by regime
    cold_metrics = [m for m in all_metrics if m.regime == 'cold']
    warm_metrics = [m for m in all_metrics if m.regime == 'warm']
    default_metrics = [m for m in all_metrics if m.regime == 'default']

    fig, ax = plt.subplots(figsize=(12, 8))

    # Plot each regime
    if cold_metrics:
        latencies = [m.duration_ms / 1000 for m in cold_metrics]  # Convert to seconds
        costs = [m.total_cost for m in cold_metrics]
        ax.scatter(latencies, costs, c='coral', label=f'Cold ({len(cold_metrics)} requests)',
                   alpha=0.7, s=80, edgecolors='darkred', linewidths=0.5)

    if warm_metrics:
        latencies = [m.duration_ms / 1000 for m in warm_metrics]
        costs = [m.total_cost for m in warm_metrics]
        ax.scatter(latencies, costs, c='steelblue', label=f'Warm ({len(warm_metrics)} requests)',
                   alpha=0.7, s=80, edgecolors='darkblue', linewidths=0.5)

    if default_metrics:
        latencies = [m.duration_ms / 1000 for m in default_metrics]
        costs = [m.total_cost for m in default_metrics]
        ax.scatter(latencies, costs, c='gray', label=f'Default ({len(default_metrics)} requests)',
                   alpha=0.5, s=60, edgecolors='black', linewidths=0.5)

    ax.set_xlabel('Latency (seconds)', fontsize=12)
    ax.set_ylabel('Cost (units)', fontsize=12)
    ax.set_title('Cost vs Latency by Regime\n(Cold Start vs Warm)', fontsize=14, fontweight='bold')
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)

    # Add trend lines if enough data
    for regime, metrics, color in [('cold', cold_metrics, 'darkred'),
                                    ('warm', warm_metrics, 'darkblue')]:
        if len(metrics) >= 3:
            latencies = np.array([m.duration_ms / 1000 for m in metrics])
            costs = np.array([m.total_cost for m in metrics])
            z = np.polyfit(latencies, costs, 1)
            p = np.poly1d(z)
            x_line = np.linspace(latencies.min(), latencies.max(), 100)
            ax.plot(x_line, p(x_line), color=color, linestyle='--', alpha=0.5, linewidth=2)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Cost vs latency scatter plot saved to {output_path}")
    plt.close()


def plot_regime_comparison_boxplot(all_metrics: List[RequestMetrics], output_path: Path) -> None:
    """Generate boxplot comparing cold vs warm regimes."""
    if not all_metrics:
        print("No metrics for boxplot.")
        return

    # Separate by regime
    cold_latencies = [m.duration_ms / 1000 for m in all_metrics if m.regime == 'cold']
    warm_latencies = [m.duration_ms / 1000 for m in all_metrics if m.regime == 'warm']
    cold_costs = [m.total_cost for m in all_metrics if m.regime == 'cold']
    warm_costs = [m.total_cost for m in all_metrics if m.regime == 'warm']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Regime Comparison: Cold vs Warm', fontsize=14, fontweight='bold')

    # Latency boxplot
    data_latency = []
    labels = []
    colors = []
    if warm_latencies:
        data_latency.append(warm_latencies)
        labels.append(f'Warm\n(n={len(warm_latencies)})')
        colors.append('steelblue')
    if cold_latencies:
        data_latency.append(cold_latencies)
        labels.append(f'Cold\n(n={len(cold_latencies)})')
        colors.append('coral')

    if data_latency:
        bp1 = ax1.boxplot(data_latency, labels=labels, patch_artist=True)
        for patch, color in zip(bp1['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        ax1.set_ylabel('Latency (seconds)', fontsize=12)
        ax1.set_title('Latency Distribution', fontsize=12)
        ax1.grid(True, alpha=0.3, axis='y')

    # Cost boxplot
    data_cost = []
    labels_cost = []
    colors_cost = []
    if warm_costs:
        data_cost.append(warm_costs)
        labels_cost.append(f'Warm\n(n={len(warm_costs)})')
        colors_cost.append('steelblue')
    if cold_costs:
        data_cost.append(cold_costs)
        labels_cost.append(f'Cold\n(n={len(cold_costs)})')
        colors_cost.append('coral')

    if data_cost:
        bp2 = ax2.boxplot(data_cost, labels=labels_cost, patch_artist=True)
        for patch, color in zip(bp2['boxes'], colors_cost):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        ax2.set_ylabel('Cost (units)', fontsize=12)
        ax2.set_title('Cost Distribution', fontsize=12)
        ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Regime comparison boxplot saved to {output_path}")
    plt.close()


def generate_regime_statistics(all_metrics: List[RequestMetrics], output_path: Path) -> Dict:
    """Generate and save regime statistics to CSV."""
    regimes = ['warm', 'cold', 'default']
    stats = {}

    for regime in regimes:
        regime_metrics = [m for m in all_metrics if m.regime == regime]
        if not regime_metrics:
            continue

        latencies = [m.duration_ms for m in regime_metrics]
        costs = [m.total_cost for m in regime_metrics]
        cold_starts = [m.cold_start_count for m in regime_metrics]

        stats[regime] = {
            'count': len(regime_metrics),
            'latency_mean_ms': statistics.mean(latencies),
            'latency_median_ms': statistics.median(latencies),
            'latency_stdev_ms': statistics.stdev(latencies) if len(latencies) > 1 else 0,
            'latency_min_ms': min(latencies),
            'latency_max_ms': max(latencies),
            'cost_mean': statistics.mean(costs) if costs and any(c > 0 for c in costs) else 0,
            'cost_median': statistics.median(costs) if costs and any(c > 0 for c in costs) else 0,
            'cost_stdev': statistics.stdev(costs) if len(costs) > 1 and any(c > 0 for c in costs) else 0,
            'avg_cold_starts': statistics.mean(cold_starts) if cold_starts else 0,
        }

    # Calculate cold start penalty
    if 'warm' in stats and 'cold' in stats:
        warm = stats['warm']
        cold = stats['cold']
        stats['cold_start_penalty'] = {
            'latency_increase_ms': cold['latency_mean_ms'] - warm['latency_mean_ms'],
            'latency_increase_pct': ((cold['latency_mean_ms'] - warm['latency_mean_ms']) / warm['latency_mean_ms'] * 100) if warm['latency_mean_ms'] > 0 else 0,
            'cost_increase': cold['cost_mean'] - warm['cost_mean'],
            'cost_increase_pct': ((cold['cost_mean'] - warm['cost_mean']) / warm['cost_mean'] * 100) if warm['cost_mean'] > 0 else 0,
        }

    # Save to CSV
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Regime', 'Count', 'Latency Mean (ms)', 'Latency Median (ms)',
                         'Latency StdDev', 'Cost Mean', 'Cost Median', 'Avg Cold Starts'])
        for regime in regimes:
            if regime in stats:
                s = stats[regime]
                writer.writerow([
                    regime.capitalize(),
                    s['count'],
                    f"{s['latency_mean_ms']:.1f}",
                    f"{s['latency_median_ms']:.1f}",
                    f"{s['latency_stdev_ms']:.1f}",
                    f"{s['cost_mean']:.2f}",
                    f"{s['cost_median']:.2f}",
                    f"{s['avg_cold_starts']:.1f}",
                ])

        # Add cold start penalty row if available
        if 'cold_start_penalty' in stats:
            p = stats['cold_start_penalty']
            writer.writerow([])
            writer.writerow(['Cold Start Penalty:'])
            writer.writerow([f"Latency Increase: {p['latency_increase_ms']:.1f}ms ({p['latency_increase_pct']:.1f}%)"])
            writer.writerow([f"Cost Increase: {p['cost_increase']:.2f} units ({p['cost_increase_pct']:.1f}%)"])

    print(f"Regime statistics saved to {output_path}")
    return stats


def print_summary_table(stats_list: List[Dict]) -> None:
    """Print formatted summary table."""
    print("\n" + "=" * 100)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 100)
    print(f"{'Experiment':<45} | {'Regime':<8} | {'Succ%':>6} | {'P50(ms)':>8} | {'P90(ms)':>8} | {'AvgCost':>8}")
    print("-" * 100)
    for s in stats_list:
        name = s['name'][:44] if len(s['name']) > 44 else s['name']
        print(f"{name:<45} | {s.get('regime', 'N/A'):<8} | {s['success_rate']:>5.1f}% | {s['p50']:>8.0f} | {s['p90']:>8.0f} | {s['avg_cost']:>8.2f}")
    print("=" * 100)


def main():
    parser = argparse.ArgumentParser(description='FAVE Experiment Analysis')
    parser.add_argument('--experiments-dir', type=str, default='experiments',
                        help='Directory containing experiment JSON files')
    args = parser.parse_args()

    results_dir = Path(args.experiments_dir)

    if not results_dir.exists():
        print(f"ERROR: Experiments directory not found: {results_dir}")
        return 1

    # Collect all experiment files
    experiment_files = sorted(results_dir.glob("results_*.json"))

    if not experiment_files:
        print(f"No experiment files found in {results_dir}")
        return 1

    print(f"Found {len(experiment_files)} experiment files")

    # Legacy analysis for summary table
    all_stats = []
    for f in experiment_files:
        s = analyze_results(f)
        if s:
            all_stats.append(s)

    # Print summary table
    print_summary_table(all_stats)

    # Collect all request metrics for detailed analysis
    all_metrics: List[RequestMetrics] = []
    for f in experiment_files:
        metrics = parse_experiment_file(f)
        all_metrics.extend(metrics)

    print(f"\nTotal requests analyzed: {len(all_metrics)}")
    print(f"  - Cold: {len([m for m in all_metrics if m.regime == 'cold'])}")
    print(f"  - Warm: {len([m for m in all_metrics if m.regime == 'warm'])}")
    print(f"  - Default: {len([m for m in all_metrics if m.regime == 'default'])}")

    # Generate all plots
    if all_stats:
        plot_results(all_stats, results_dir / "results_summary.png")

    if all_metrics:
        plot_cost_vs_latency_scatter(all_metrics, results_dir / "cost_vs_latency_cold_warm.png")
        plot_regime_comparison_boxplot(all_metrics, results_dir / "regime_comparison.png")
        stats = generate_regime_statistics(all_metrics, results_dir / "regime_statistics.csv")

        # Print cold start penalty summary
        if 'cold_start_penalty' in stats:
            p = stats['cold_start_penalty']
            print("\n" + "=" * 60)
            print("COLD START PENALTY ANALYSIS")
            print("=" * 60)
            print(f"Latency Increase: {p['latency_increase_ms']:.1f}ms ({p['latency_increase_pct']:.1f}%)")
            print(f"Cost Increase: {p['cost_increase']:.2f} units ({p['cost_increase_pct']:.1f}%)")
            print("=" * 60)

    print("\nAnalysis complete!")
    return 0


if __name__ == "__main__":
    exit(main())
