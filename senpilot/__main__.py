import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

from .models import CATEGORIES
from .retrieval import retrieve


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieve up to ten regulatory documents through the browser")
    parser.add_argument("matter", help="Matter number, for example M12205")
    parser.add_argument("category", choices=CATEGORIES)
    parser.add_argument("--limit", type=int, default=10, help="Successful file limit from 0 to 10; 0 lists metadata")
    parser.add_argument("--output", type=Path, help="A directory that does not already exist")
    args = parser.parse_args()
    matter = args.matter.strip().upper()
    if re.fullmatch(r"M\d{5}", matter) is None:
        parser.error("matter must be M followed by five digits")
    if not 0 <= args.limit <= 10:
        parser.error("--limit must be between zero and ten")
    name = f"{matter}_{args.category.replace(' ', '_')}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}"
    output = args.output or Path("artifacts/retrieval") / name
    if output.exists():
        parser.error("--output already exists; choose a fresh directory")
    report = retrieve(matter, args.category, output, args.limit, progress=lambda message: print(message, flush=True))
    print(f"Status: {report['status']}; downloaded {report['downloaded_count']}; "
          f"skipped {len(report['unavailable'])}; failures {len(report['failures'])}; "
          f"file warnings {report.get('validation_warning_count', 0)}")
    print(f"Report: {output / 'report.json'}")
    if report.get("error"):
        print(report["error"]["message"], file=sys.stderr)
    return 0 if report["status"] in {"complete", "empty", "metadata_only"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
