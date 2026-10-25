"""Export an OpenAPI snapshot without credentials or database access."""

import argparse
import json
from pathlib import Path

from personalization.interfaces.http.app import create_http_app


def main() -> int:
    """Export a stable contract or verify its committed copy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    content = (
        json.dumps(
            create_http_app().openapi(),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
        )
        + "\n"
    )
    output: Path = arguments.output
    if arguments.check:
        if (
            not output.is_file()
            or output.read_text(encoding="utf-8") != content
        ):
            parser.exit(1, "The committed OpenAPI contract is out of date.\n")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
