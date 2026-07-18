"""Download the optional upstream legacy medical dataset with checksum verification."""
from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path


DEFAULT_URL = (
    "https://raw.githubusercontent.com/liuhuanyong/"
    "QASystemOnMedicalKG/master/data/medical.json"
)
EXPECTED_SHA256 = "87b93493ea788c686325ff2b7109b4135b4754cec09f534dce7bf13ea0ec2055"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "medical.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Download optional legacy GraphRAG seed data.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-checksum", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".download")
    print(f"Downloading legacy dataset to {output}")
    try:
        urllib.request.urlretrieve(args.url, temporary)
        actual = sha256(temporary)
        if not args.skip_checksum and args.url == DEFAULT_URL and actual != EXPECTED_SHA256:
            raise RuntimeError(
                f"checksum mismatch: expected {EXPECTED_SHA256}, received {actual}"
            )
        temporary.replace(output)
        print(f"Downloaded {output.stat().st_size / 1024 / 1024:.1f} MiB (sha256={actual})")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
