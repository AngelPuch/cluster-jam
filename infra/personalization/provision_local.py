"""Create local development secrets without replacing existing ones."""

import os
import secrets
from pathlib import Path


def provision_secrets() -> None:
    """Keep secret files outside Git and preserve volume credentials."""
    secret_directory = Path(__file__).resolve().parent / ".secrets"
    if secret_directory.is_symlink():
        raise RuntimeError("The secret directory must not be a symlink")
    secret_directory.mkdir(mode=0o700, exist_ok=True)
    if os.name == "posix":
        secret_directory.chmod(0o700)
    for name in ("postgres_admin_password", "personalization_db_password"):
        path = secret_directory / name
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("A secret must be a regular file")
            if not path.read_text(encoding="utf-8").strip():
                raise RuntimeError("An existing secret is empty")
            continue
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(secrets.token_urlsafe(32) + "\n")
        if os.name == "posix":
            path.chmod(0o444)


if __name__ == "__main__":
    provision_secrets()
    print("Local secret files are ready; existing values were preserved")
