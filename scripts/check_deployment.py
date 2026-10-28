"""Validate Compose against its official schema; this does not build the image."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import urlopen

import jsonschema
import yaml


SCHEMA_URL = "https://raw.githubusercontent.com/compose-spec/compose-spec/master/schema/compose-spec.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, help="An existing schema file for offline validation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.schema:
        raw = args.schema.read_bytes()
    else:
        with urlopen(SCHEMA_URL, timeout=30) as response:
            raw = response.read()
        cache = root / "artifacts/deployment/compose-schema.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(raw)
    schema = json.loads(raw)
    compose = yaml.safe_load((root / "deploy/compose.yaml").read_text())
    jsonschema.validate(compose, schema)
    print(f"Compose schema validation passed; schema SHA256 {sha256(raw).hexdigest()}")
    print("Container build and Linux runtime validation still require Docker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
