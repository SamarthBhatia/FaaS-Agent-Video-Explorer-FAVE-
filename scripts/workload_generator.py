import argparse
import json
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import httpx

class WorkloadGenerator:
    def __init__(self, gateway_url: str, output_dir: Path):
        self.gateway_url = gateway_url.rstrip("/")
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.Client(timeout=None)

    def invoke_orchestrator(self, video_uri: str, profile: str = "default", semaphore: threading.Semaphore = None) -> Dict[str, Any]:
        # Note: Semaphore is acquired by the producer loop before calling this
        url = f"{self.gateway_url}/function/orchestrator"
        payload = {
            "video_uri": video_uri,
            "profile": profile
        }
        
        start_time = time.perf_counter()
        timestamp = datetime.now().isoformat()
        
        try:
            response = self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            status = "success"
        except Exception as e:
            data = {"error": str(e)}
            status = "failure"
        finally:
            if semaphore:
                semaphore.release()
        
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        
        return {
            "timestamp": timestamp,
            "duration_ms": duration_ms,
            "status": status,
            "response": data,
            "profile": profile
        }

    def run_steady(self, video_uri: str, total_requests: int, rps: float, profile: str, concurrency: int):
        print(f"Running steady workload: {total_requests} requests at {rps} RPS (profile: {profile}, max_concurrency: {concurrency})")
        results = []
        interval = 1.0 / rps if rps > 0 else 0
        semaphore = threading.Semaphore(concurrency)
        
        with ThreadPoolExecutor(max_workers=concurrency + 5) as executor:
            futures = []
            start_workload = time.perf_counter()
            for i in range(total_requests):
                # Acquire semaphore BEFORE sleeping/submitting to pace arrivals correctly
                semaphore.acquire()
                
                expected_start = start_workload + (i * interval)
                now = time.perf_counter()
                if now < expected_start:
                    time.sleep(expected_start - now)
                
                futures.append(executor.submit(self.invoke_orchestrator, video_uri, profile, semaphore))
            
            for future in futures:
                results.append(future.result())
        
        self.save_results(results, f"steady_{profile}_{int(rps)}rps_{total_requests}req")

    def run_burst(self, video_uri: str, burst_size: int, profile: str):
        print(f"Running burst workload: {burst_size} concurrent requests (profile: {profile})")
        results = []
        
        with ThreadPoolExecutor(max_workers=burst_size) as executor:
            futures = [executor.submit(self.invoke_orchestrator, video_uri, profile) for _ in range(burst_size)]
            for future in futures:
                results.append(future.result())
        
        self.save_results(results, f"burst_{profile}_{burst_size}req")

    def save_results(self, results: List[Dict[str, Any]], name: str):
        filename = self.output_dir / f"results_{name}_{int(time.time())}.json"
        with open(filename, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FAVE Workload Generator")
    parser.add_argument("--gateway", default="http://localhost:8080", help="OpenFaaS gateway URL")
    parser.add_argument("--video", required=True, help="Input video URI/URL")
    parser.add_argument("--pattern", choices=["steady", "burst"], default="steady", help="Workload pattern")
    parser.add_argument("--requests", type=int, default=1, help="Total requests for steady or burst size")
    parser.add_argument("--rps", type=float, default=1.0, help="Requests per second for steady pattern")
    parser.add_argument("--concurrency", type=int, default=50, help="Max concurrent requests for steady workload")
    parser.add_argument("--profile", default="default", help="Configuration profile (e.g., cold, warm)")
    parser.add_argument("--output", default="experiments", help="Output directory for results")
    
    args = parser.parse_args()
    
    generator = WorkloadGenerator(args.gateway, Path(args.output))
    
    if args.pattern == "steady":
        generator.run_steady(args.video, args.requests, args.rps, args.profile, args.concurrency)
    elif args.pattern == "burst":
        generator.run_burst(args.video, args.requests, args.profile)
