"""
Utilities for interacting with the shared S3/MinIO artifact store.

Every function in the FAVE pipeline should use these helpers instead of
rolling bespoke boto3 code so credentials and logging remain consistent.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urlparse

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

DEFAULT_BUCKET = os.getenv("ARTIFACT_BUCKET")


def _parse_s3_uri(uri: str) -> Tuple[str, str]:
    """
    Parse an S3-style URI and return (bucket, key).

    Supports URIs like:
    - s3://bucket/key
    - s3a://bucket/key
    - bucket/key  (bucket inferred from ARTIFACT_BUCKET)
    """
    if not uri:
        raise ValueError("URI cannot be empty")

    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()

    if scheme in {"s3", "s3a", "s3n"}:
        bucket = parsed.netloc or DEFAULT_BUCKET
        key = parsed.path.lstrip("/")
    else:
        bucket = DEFAULT_BUCKET
        key = uri.lstrip("/")

    if not bucket:
        raise ValueError(f"No bucket specified for URI '{uri}' and ARTIFACT_BUCKET not set")

    if not key:
        raise ValueError(f"No key component found in URI '{uri}'")

    return bucket, key


@lru_cache(maxsize=1)
def _s3_client():
    """
    Lazily instantiate a boto3 S3 client configured for MinIO/S3 usage.
    """
    session = boto3.session.Session()
    endpoint = os.getenv("ARTIFACT_ENDPOINT")
    region = os.getenv("ARTIFACT_REGION", "us-east-1")
    access_key = os.getenv("ARTIFACT_ACCESS_KEY")
    secret_key = os.getenv("ARTIFACT_SECRET_KEY")

    return session.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )


def download_file(uri: str, destination: str | Path) -> Path:
    """Download an object to the specified path."""
    bucket, key = _parse_s3_uri(uri)
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _s3_client().download_file(bucket, key, str(dest))
    return dest


def upload_file(source: str | Path, uri: str, extra_args: Optional[Dict] = None) -> str:
    """Upload a local file to the bucket."""
    bucket, key = _parse_s3_uri(uri)
    _s3_client().upload_file(str(source), bucket, key, ExtraArgs=extra_args or {})
    return f"s3://{bucket}/{key}"


def list_objects(prefix: str, max_keys: int = 1000) -> Iterable[Dict]:
    """Iterate over objects under the specified prefix."""
    bucket, key_prefix = _parse_s3_uri(prefix)
    paginator = _s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix, PaginationConfig={"MaxItems": max_keys}):
        for obj in page.get("Contents", []):
            yield obj


def object_exists(uri: str) -> bool:
    """Return True if the object exists."""
    bucket, key = _parse_s3_uri(uri)
    try:
        _s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as exc:
        if exc.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return False
        raise


def read_json(uri: str) -> Dict:
    """Download and parse a JSON object."""
    bucket, key = _parse_s3_uri(uri)
    obj = _s3_client().get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode("utf-8"))


def write_json(data: Dict, uri: str) -> str:
    """Serialize data as JSON and upload."""
    tmp_path = Path("/tmp") / f"json-{os.getpid()}.tmp"
    tmp_path.write_text(json.dumps(data, indent=2))
    try:
        return upload_file(tmp_path, uri, extra_args={"ContentType": "application/json"})
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
