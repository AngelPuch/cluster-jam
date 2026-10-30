"""Verify shared deployment uses the consumer's canonical broker contract."""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "cluster_jam_prepare", ROOT / "infra" / "deploy" / "prepare.py"
)
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)
TOPOLOGY = json.loads(
    (
        ROOT
        / "services"
        / "profileService"
        / "src"
        / "infrastructure"
        / "messaging"
        / "profile-topology.json"
    ).read_text(encoding="utf-8")
)


class BrokerDefinitionsTest(unittest.TestCase):
    def test_shared_definitions_preserve_auth_and_profile_topology(self) -> None:
        with tempfile.TemporaryDirectory(prefix="profile-definitions-") as tmp:
            directory = Path(tmp)
            shared = directory / "shared"
            auth = directory / "auth"
            (shared / ".secrets").mkdir(parents=True)
            (auth / ".secrets").mkdir(parents=True)
            with (
                patch.object(PREPARE, "SHARED", shared),
                patch.object(PREPARE, "AUTH", auth),
            ):
                PREPARE.prepare_definitions()
                path = shared / ".secrets" / "rabbitmq_definitions.json"
                first = path.read_bytes()
                PREPARE.prepare_definitions()
                self.assertEqual(path.read_bytes(), first)
                definitions = json.loads(first)
            permissions = {entry["user"]: entry for entry in definitions["permissions"]}
            self.assertEqual(
                permissions["auth-publisher"]["write"], r"^identity\.events$"
            )
            for key, value in TOPOLOGY["consumerPermissions"].items():
                self.assertEqual(permissions["profile-consumer"][key], value)
            queues = {queue["name"]: queue for queue in definitions["queues"]}
            self.assertEqual(queues[TOPOLOGY["queue"]]["arguments"], {})
            for retry in TOPOLOGY["retries"]:
                args = queues[retry["queue"]]["arguments"]
                self.assertEqual(args["x-message-ttl"], retry["delayMs"])
                self.assertEqual(args["x-queue-type"], "quorum")
                self.assertEqual(args["x-overflow"], "reject-publish")
                self.assertEqual(args["x-dead-letter-strategy"], "at-least-once")
            self.assertEqual(len(definitions["bindings"]), 5)

    def test_consumer_permissions_do_not_allow_identity_writes(self) -> None:
        permissions = TOPOLOGY["consumerPermissions"]
        self.assertIsNone(re.fullmatch(permissions["write"], "identity.events"))
        self.assertIsNone(re.fullmatch(permissions["configure"], "identity.events"))
        self.assertIsNotNone(re.fullmatch(permissions["read"], "identity.events"))
        for queue in TOPOLOGY["queues"]:
            self.assertIsNotNone(re.fullmatch(permissions["configure"], queue["name"]))
            self.assertIsNone(re.fullmatch(permissions["write"], "orders.events"))


if __name__ == "__main__":
    unittest.main()
