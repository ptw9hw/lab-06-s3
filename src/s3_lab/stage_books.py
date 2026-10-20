#!/usr/bin/env python3
"""Download Project Gutenberg books and stage them in a public S3 bucket.

Usage: stage_books.py BOOK_LIST INDEX_HTML BUCKET
Example: stage_books.py book_urls.txt index.html public-mst3k
"""

import json
import logging
import os
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# One shared S3 client for every function (not the anonymous read-only client).
s3 = boto3.client("s3", region_name="us-east-1")


def parse_args():
    """Return (list_file, index_path, bucket) from the command line."""
    if len(sys.argv) < 4:
        log.error("Usage: %s BOOK_LIST INDEX_HTML BUCKET", sys.argv[0])
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download each URL in list_file into dest_dir and return the local paths."""
    os.makedirs(dest_dir, exist_ok=True)

    with open(list_file) as f:
        urls = [line.strip() for line in f if line.strip()]
    log.info("Found %d book URLs in %s", len(urls), list_file)

    paths = []
    for url in urls:
        # Keep the original file name so the links in index.html still work.
        path = os.path.join(dest_dir, url.rsplit("/", 1)[-1])
        if os.path.exists(path):
            log.info("Already downloaded, skipping: %s", path)
            paths.append(path)
            continue
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as out:
                out.write(response.content)
            log.info("Downloaded %s", path)
            paths.append(path)
        except requests.RequestException as e:
            log.error(f"Error downloading {url}: {e}")
        # Be polite to Project Gutenberg's servers.
        time.sleep(1)

    log.info("%d of %d books available locally", len(paths), len(urls))
    return paths


def create_bucket(bucket):
    """Create the bucket unless it already exists; return True if it exists afterwards."""
    try:
        s3.head_bucket(Bucket=bucket)
        log.info("Bucket %s already exists", bucket)
        return True
    except ClientError:
        log.info("Bucket %s not found, creating it", bucket)

    try:
        # us-east-1 does not take a CreateBucketConfiguration.
        s3.create_bucket(Bucket=bucket)
        log.info("Created bucket %s", bucket)
        return True
    except ClientError as e:
        log.error(f"Error creating bucket {bucket}: {e}")
        return False


def make_public(bucket):
    """Turn off Block Public Access and allow anyone to read the bucket's objects."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/*",
            }
        ],
    }
    try:
        # Block Public Access must be off before S3 accepts a public policy.
        s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        log.info("Turned off Block Public Access for %s", bucket)
        s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
        log.info("Attached public-read policy to %s", bucket)
        return True
    except ClientError as e:
        log.error(f"Error making bucket {bucket} public: {e}")
        return False


def upload_files(bucket, file_paths):
    """Upload each file to the top level of the bucket; return the number uploaded."""
    uploaded = 0
    for path in file_paths:
        key = os.path.basename(path)  # pg1342.txt, not books/pg1342.txt
        try:
            with open(path, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType="text/plain; charset=utf-8",
                )
            log.info("Uploaded %s", key)
            uploaded += 1
        except (ClientError, OSError) as e:
            log.error(f"Error uploading {path}: {e}")
    log.info("Uploaded %d of %d books", uploaded, len(file_paths))
    return uploaded


def upload_index(bucket, index_path):
    """Upload the index page as index.html; return True on success."""
    if not os.path.exists(index_path):
        log.error("Index file not found: %s", index_path)
        return False
    try:
        with open(index_path, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key="index.html",
                Body=f,
                ContentType="text/html",
            )
        log.info("Uploaded index.html")
        return True
    except ClientError as e:
        log.error(f"Error uploading {index_path}: {e}")
        return False


def main():
    """Download the books, stage them in a public bucket, and print the index URL."""
    list_file, index_path, bucket = parse_args()

    paths = download_books(list_file, "books")
    if not paths:
        log.error("No books were downloaded")
        sys.exit(1)

    if not create_bucket(bucket):
        sys.exit(1)
    if not make_public(bucket):
        sys.exit(1)

    uploaded = upload_files(bucket, paths)
    index_ok = upload_index(bucket, index_path)

    url = f"https://{bucket}.s3.amazonaws.com/index.html"
    if uploaded == len(paths) and index_ok:
        log.info("Success: all %d books and index.html are staged", uploaded)
    else:
        log.error("Finished with errors: %d of %d books uploaded, index uploaded: %s",
                  uploaded, len(paths), index_ok)
    log.info("Public index page: %s", url)


if __name__ == "__main__":
    main()
