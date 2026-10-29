"""Regenerate deterministic protobuf bindings without editing them."""

import argparse
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

FILES = (
    "personalization_pb2.py",
    "personalization_pb2.pyi",
    "personalization_pb2_grpc.py",
)


def generate(proto: Path, output: Path, *, check: bool = False) -> None:
    if proto.name != "personalization.proto" or not proto.is_file():
        raise ValueError("The versioned personalization.proto is required")
    with TemporaryDirectory() as directory:
        temporary = Path(directory)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "grpc_tools.protoc",
                f"--proto_path={proto.parent.resolve()}",
                f"--python_out={temporary}",
                f"--pyi_out={temporary}",
                f"--grpc_python_out={temporary}",
                str(proto.resolve()),
            ],
            check=True,
            timeout=30,
            capture_output=True,
        )
        for name in FILES:
            content = (temporary / name).read_text(encoding="utf-8")
            if name.endswith("_grpc.py"):
                content = content.replace(
                    "import personalization_pb2 as ",
                    "from . import personalization_pb2 as ",
                )
            target = output / name
            if check:
                if (
                    not target.is_file()
                    or target.read_text(encoding="utf-8") != content
                ):
                    raise ValueError(
                        "The generated protobuf contract is stale"
                    )
            else:
                output.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proto", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    generate(arguments.proto, arguments.output, check=arguments.check)


if __name__ == "__main__":
    main()
