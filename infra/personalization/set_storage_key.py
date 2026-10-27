"""Store a backend Storage key locally without echoing its value."""

import getpass
import os
import re
import tempfile
from pathlib import Path


def main() -> int:
    """Save only the dedicated ignored Storage secret file."""
    value = getpass.getpass("Supabase backend key (sb_secret_...): ")
    if re.fullmatch(r"sb_secret_[A-Za-z0-9_-]{20,200}", value) is None:
        print("Invalid backend secret key; no file was changed")
        return 1
    directory = Path(__file__).resolve().parent / ".secrets"
    directory.mkdir(exist_ok=True, mode=0o700)
    target = directory / "supabase_storage_key"
    descriptor, temporary = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(
            descriptor, "w", encoding="utf-8", newline="\n"
        ) as stream:
            stream.write(value)
        if os.name != "nt":
            Path(temporary).chmod(0o444)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print("Storage key saved in the ignored local secret file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
