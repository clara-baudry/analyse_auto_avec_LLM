#!/usr/bin/env python3
"""
run_on_minio.py — Run table_to_md.convert() on a file stored in MinIO.

Usage:
    python run_on_minio.py <input path in S3> <output path in S3>

Example:
    python run_on_minio.py username/data/metadonnees.ods username/data/metadonnees.md

Credentials are automatically injected by Onyxia as environment variables.
"""

import os
import sys
from pathlib import Path

import s3fs

from table_to_md import convert


def main(input_s3: str, output_s3: str) -> None:
    fs = s3fs.S3FileSystem(
        client_kwargs={"endpoint_url": "https://" + os.environ["AWS_S3_ENDPOINT"]}
    )

    # Infer a local temp name that preserves the extension (needed by convert())
    suffix = Path(input_s3).suffix
    tmp = Path(f"/tmp/input{suffix}")

    # Download from MinIO
    print(f"↓ Downloading {input_s3} ...")
    with fs.open(input_s3, "rb") as f_in:
        tmp.write_bytes(f_in.read())

    # Convert
    print("⚙ Converting ...")
    markdown = convert(tmp)

    # Upload back to MinIO
    print(f"↑ Uploading to {output_s3} ...")
    with fs.open(output_s3, "w", encoding="utf-8") as f_out:
        f_out.write(markdown)

    print(f"✓ Done: {input_s3} → {output_s3}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    main(sys.argv[1], sys.argv[2])
