"""Package a saved report without opening a browser or downloading again."""

import argparse
from pathlib import Path
import sys

from .packaging import PackagingError, package_report


def print_summary(summary: dict, output: Path) -> None:
    print(f"Package: {summary['status']}; retrieval: {summary['source_status']}; "
          f"files: {summary['manifest']['file_count']}")
    if summary["archive"]:
        archive = summary["archive"]
        print(f"ZIP: {output / archive['path']} ({archive['bytes']} bytes; SHA256 verified)")
    print(f"Package summary: {output / 'package.json'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify a ZIP from a saved retrieval report")
    parser.add_argument("report", type=Path, help="The existing retrieval report.json")
    parser.add_argument("--output", type=Path, help="A fresh directory; defaults to package/ beside the report")
    args = parser.parse_args()
    output = args.output or args.report.parent / "package"
    try:
        summary = package_report(args.report, output)
    except (PackagingError, OSError) as error:
        print(f"Packaging failed: {error}", file=sys.stderr)
        return 2
    print_summary(summary, output)
    return 0 if summary["source_status"] in {"complete", "empty", "metadata_only"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
