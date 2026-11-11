"""Enforce dependency direction at the service boundaries."""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src" / "personalization"


def test_business_is_independent_of_frameworks_and_adapters() -> None:
    forbidden = (
        "personalization.infrastructure",
        "personalization.interfaces",
        "fastapi",
        "grpc",
        "pydantic",
        "sqlalchemy",
        "PIL",
    )
    for path in (SOURCE / "application").rglob("*.py"):
        assert_no_imports(path, forbidden)


def test_rpc_does_not_depend_on_http_entry_points() -> None:
    for path in (SOURCE / "interfaces" / "grpc").glob("*.py"):
        assert_no_imports(path, ("personalization.interfaces.http",))


def test_http_does_not_query_database_adapters_directly() -> None:
    for path in (SOURCE / "interfaces" / "http").rglob("*.py"):
        assert_no_imports(
            path, ("sqlalchemy", "personalization.infrastructure.database")
        )


def assert_no_imports(path: Path, forbidden: tuple[str, ...]) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        modules = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        for module in modules:
            assert not any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in forbidden
            ), f"{path.relative_to(SOURCE)} imports {module}"
