"""Fail when a new public operation lacks explicit QA evidence."""

import ast
import json
from pathlib import Path

from personalization.interfaces.grpc.generated import personalization_pb2
from personalization.interfaces.http.app import create_http_app

DIRECTORY = Path(__file__).resolve().parent
SERVICE = DIRECTORY.parents[1]


def test_every_exposed_operation_has_traceable_behavior_and_policy() -> None:
    matrix = json.loads((DIRECTORY / "requirements.json").read_bytes())
    document = create_http_app().openapi()
    exposed = {
        f"{method.upper()} {path}"
        for path, methods in document["paths"].items()
        for method in methods
        if method in {"get", "post", "put", "patch", "delete"}
    }
    descriptor = personalization_pb2.DESCRIPTOR
    exposed.update(
        f"RPC {service.full_name}/{method.name}"
        for service in descriptor.services_by_name.values()
        for method in service.methods
    )
    rows = matrix["operations"]
    assert len(rows) == len({row["operation"] for row in rows})
    assert {row["operation"] for row in rows} == exposed
    requirements = {row["id"] for row in matrix["requirements"]}
    assert requirements == {
        "RF08",
        "RF10",
        "RF11",
        "RF12",
        "RF13",
        "RF14",
        "RF15",
        "RF30",
        *(f"RNF{number:02}" for number in range(1, 12)),
    }
    assert matrix["line_coverage_is_functionality_coverage"] is False
    for row in rows:
        assert row["requirements"]
        assert set(row["requirements"]) <= requirements
        assert row["access_policy"]
        for field in ("behavior_tests", "permission_or_availability_tests"):
            assert row[field]
            for reference in row[field]:
                filename, function = reference.split("::")
                source = SERVICE / filename
                assert source.is_relative_to(SERVICE / "test")
                functions = {
                    node.name
                    for node in ast.parse(
                        source.read_text(encoding="utf-8")
                    ).body
                    if isinstance(node, ast.FunctionDef)
                }
                assert function in functions, reference
