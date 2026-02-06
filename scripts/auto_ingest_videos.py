#!/usr/bin/env python3
"""
Automated Video Ingestion Script

Downloads videos from configured sources and uploads them to MinIO.
Generates a list of S3 URIs for use with JMeter or workload generator.

Usage:
    python3 scripts/auto_ingest_videos.py
    python3 scripts/auto_ingest_videos.py --sources datasets/video_sources.csv
    python3 scripts/auto_ingest_videos.py --limit 3  # Only download first 3 videos
"""

import argparse
import csv
import io
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import boto3
import requests
from botocore.client import Config

# Configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "faveadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "favesecret")
BUCKET_NAME = os.getenv("ARTIFACT_BUCKET", "fave-artifacts")
INPUT_PREFIX = "input"

# Default sources file
DEFAULT_SOURCES = Path(__file__).parent.parent / "datasets" / "video_sources.csv"


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
    """Ensure bucket exists."""
    try:
        client.head_bucket(Bucket=BUCKET_NAME)
    except Exception:
        client.create_bucket(Bucket=BUCKET_NAME)
        print(f"Created bucket: {BUCKET_NAME}")


def check_video_exists(client, key: str) -> bool:
    """Check if video already exists in MinIO."""
    try:
        client.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except Exception:
        return False


def download_video(url: str, name: str) -> Tuple[bytes, int]:
    """
    Download video from URL with progress indicator.

    Returns: (video_bytes, size_bytes)
    """
    print(f"  Downloading from {url[:60]}...")

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0
    chunks = []

    for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = (downloaded / total_size) * 100
                print(f"    Progress: {downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB ({pct:.0f}%)", end='\r')

    print()  # New line after progress

    video_bytes = b''.join(chunks)
    return video_bytes, len(video_bytes)


def upload_to_minio(client, video_bytes: bytes, key: str) -> str:
    """Upload video bytes to MinIO."""
    buf = io.BytesIO(video_bytes)
    client.upload_fileobj(
        buf,
        BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "video/mp4"}
    )
    return f"s3://{BUCKET_NAME}/{key}"


def load_video_sources(sources_file: Path) -> List[dict]:
    """Load video sources from CSV file."""
    if not sources_file.exists():
        print(f"ERROR: Sources file not found: {sources_file}")
        return []

    videos = []
    with open(sources_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            videos.append({
                'name': row['name'],
                'url': row['url'],
                'description': row.get('description', ''),
                'size_mb': int(row.get('size_mb', 0)),
            })

    return videos


def ingest_videos(
    sources_file: Path,
    limit: int = 0,
    force: bool = False,
    dry_run: bool = False,
) -> List[str]:
    """
    Main ingestion function.

    Args:
        sources_file: Path to CSV file with video sources
        limit: Maximum number of videos to ingest (0 = all)
        force: Re-download even if video exists
        dry_run: Only print what would be done

    Returns:
        List of S3 URIs for ingested videos
    """
    videos = load_video_sources(sources_file)

    if not videos:
        print("No video sources found.")
        return []

    if limit > 0:
        videos = videos[:limit]

    print(f"\n{'='*60}")
    print(f"FAVE Video Ingestion")
    print(f"{'='*60}")
    print(f"Sources file: {sources_file}")
    print(f"MinIO endpoint: {MINIO_ENDPOINT}")
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Videos to process: {len(videos)}")
    print(f"{'='*60}\n")

    if dry_run:
        print("DRY RUN - No actual downloads or uploads")
        print()

    client = get_s3_client()
    ensure_bucket(client)

    ingested_uris = []

    for i, video in enumerate(videos, 1):
        name = video['name']
        url = video['url']
        key = f"{INPUT_PREFIX}/{name}.mp4"
        s3_uri = f"s3://{BUCKET_NAME}/{key}"

        print(f"[{i}/{len(videos)}] {name}")
        print(f"  Description: {video['description']}")
        print(f"  Expected size: ~{video['size_mb']}MB")

        # Check if already exists
        if not force and check_video_exists(client, key):
            print(f"  Status: Already exists (skipping)")
            print(f"  URI: {s3_uri}")
            ingested_uris.append(s3_uri)
            print()
            continue

        if dry_run:
            print(f"  Would download: {url}")
            print(f"  Would upload to: {s3_uri}")
            ingested_uris.append(s3_uri)
            print()
            continue

        try:
            # Download
            start_time = time.time()
            video_bytes, size = download_video(url, name)
            download_time = time.time() - start_time

            # Upload
            start_time = time.time()
            uri = upload_to_minio(client, video_bytes, key)
            upload_time = time.time() - start_time

            print(f"  Downloaded: {size / (1024*1024):.1f}MB in {download_time:.1f}s")
            print(f"  Uploaded: {upload_time:.1f}s")
            print(f"  URI: {uri}")

            ingested_uris.append(uri)

        except Exception as e:
            print(f"  ERROR: {str(e)}")

        print()

    # Save URIs to file for JMeter
    uris_file = sources_file.parent / "ingested_uris.txt"
    with open(uris_file, 'w') as f:
        for uri in ingested_uris:
            f.write(uri + '\n')
    print(f"Ingested URIs saved to: {uris_file}")

    # Also save as CSV for JMeter CSV Data Set Config
    jmeter_csv = sources_file.parent / "jmeter_videos.csv"
    with open(jmeter_csv, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['video_uri', 'name'])
        for uri, video in zip(ingested_uris, videos):
            writer.writerow([uri, video['name']])
    print(f"JMeter CSV saved to: {jmeter_csv}")

    print(f"\n{'='*60}")
    print(f"Ingestion complete: {len(ingested_uris)} videos ready")
    print(f"{'='*60}")

    return ingested_uris


def main():
    parser = argparse.ArgumentParser(description='Automated Video Ingestion for FAVE')
    parser.add_argument(
        '--sources',
        type=Path,
        default=DEFAULT_SOURCES,
        help=f'Path to video sources CSV (default: {DEFAULT_SOURCES})',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Maximum number of videos to ingest (0 = all)',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Re-download even if video already exists in MinIO',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without actually downloading',
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List existing videos in MinIO',
    )

    args = parser.parse_args()

    if args.list:
        client = get_s3_client()
        try:
            response = client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=INPUT_PREFIX)
            print(f"\nExisting videos in s3://{BUCKET_NAME}/{INPUT_PREFIX}/:")
            for obj in response.get('Contents', []):
                size_mb = obj['Size'] / (1024 * 1024)
                print(f"  - {obj['Key']} ({size_mb:.1f}MB)")
        except Exception as e:
            print(f"ERROR: {e}")
        return 0

    uris = ingest_videos(
        sources_file=args.sources,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
    )

    return 0 if uris else 1


if __name__ == "__main__":
    sys.exit(main())
