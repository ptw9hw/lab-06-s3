#!/bin/bash
# Download one book, upload it to a private S3 bucket, and print a presigned URL to it.
# Usage: ./share_book.sh BOOK_URL BUCKET EXPIRES_IN_SECONDS
set -euo pipefail

# Check that all three arguments were given.
if [ "$#" -lt 3 ]; then
    echo "Usage: $0 BOOK_URL BUCKET EXPIRES_IN_SECONDS" >&2
    echo "Example: $0 https://www.gutenberg.org/cache/epub/345/pg345.txt secret-mst3k 604800" >&2
    exit 1
fi

URL="$1"
BUCKET="$2"
EXPIRES="$3"

# Keep the file name from the URL, e.g. pg345.txt.
FILE="$(basename "$URL")"
LOCAL_PATH="books/$FILE"

# Download the book into the books/ folder.
mkdir -p books
echo "Downloading $URL to $LOCAL_PATH"
curl -fsSL "$URL" -o "$LOCAL_PATH"

# Create the bucket unless it already exists.
if aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    echo "Bucket $BUCKET already exists"
else
    echo "Creating bucket $BUCKET"
    aws s3 mb "s3://$BUCKET" --region us-east-1
fi

# Upload the book; the bucket and the book stay private.
echo "Uploading $FILE to s3://$BUCKET/"
aws s3 cp "$LOCAL_PATH" "s3://$BUCKET/$FILE" --content-type "text/plain; charset=utf-8"

# Presign a URL that expires after EXPIRES seconds and print it.
echo "Presigned URL (expires in $EXPIRES seconds):"
aws s3 presign "s3://$BUCKET/$FILE" --expires-in "$EXPIRES"
