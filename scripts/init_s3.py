"""Ensure the S3 bucket used for invoice blobs exists."""
from __future__ import annotations

import os

import boto3
import botocore.exceptions


def main() -> None:
    s3 = boto3.resource(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    )
    bucket = os.getenv("S3_BUCKET", "invoice-blobs")
    try:
        s3.create_bucket(Bucket=bucket)
    except botocore.exceptions.ClientError:
        pass
    print("S3 bucket ready.")


if __name__ == "__main__":  # pragma: no cover
    main()
