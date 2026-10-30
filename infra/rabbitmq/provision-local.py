"""Provision the local development broker only; uses fictitious local credentials."""
import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:15672/api"
AUTH = base64.b64encode(b"clusterjam:local-development-only").decode()


def call(method, path, body):
    request = Request(
        BASE_URL + path,
        data=json.dumps(body).encode(),
        method=method,
        headers={"Authorization": "Basic " + AUTH, "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        response.read()


call("PUT", "/vhosts/clusterjam-test", {})
call("PUT", "/permissions/clusterjam-test/clusterjam", {"configure": ".*", "write": ".*", "read": ".*"})
call("PUT", "/exchanges/clusterjam/identity.events", {"type": "topic", "durable": True, "auto_delete": False, "internal": False, "arguments": {}})
call("PUT", "/queues/clusterjam/profile.identity.user-registered.v1", {"durable": True, "auto_delete": False, "arguments": {}})
call("POST", "/bindings/clusterjam/e/identity.events/q/profile.identity.user-registered.v1", {"routing_key": "identity.user.registered.v1", "arguments": {}})
call("PUT", "/users/auth-publisher", {"password": "local-publisher-only", "tags": ""})
call("PUT", "/permissions/clusterjam/auth-publisher", {"configure": "^identity\\.events$", "write": "^identity\\.events$", "read": "^$"})
topology = json.loads(
    (Path(__file__).resolve().parents[2] / "services" / "profileService"
     / "src" / "infrastructure" / "messaging" / "profile-topology.json")
    .read_text(encoding="utf-8")
)
for exchange in topology["exchanges"]:
    call("PUT", "/exchanges/clusterjam/" + exchange["name"],
         {**exchange, "auto_delete": False, "internal": False, "arguments": {}})
for queue in topology["queues"]:
    call("PUT", "/queues/clusterjam/" + queue["name"],
         {**queue, "auto_delete": False})
for binding in topology["bindings"]:
    call("POST", "/bindings/clusterjam/e/" + binding["source"]
         + "/q/" + binding["destination"],
         {"routing_key": binding["routing_key"], "arguments": {}})
call("PUT", "/users/profile-consumer", {"password": "local-profile-only", "tags": ""})
call("PUT", "/permissions/clusterjam/profile-consumer", topology["consumerPermissions"])
print("Local RabbitMQ topology and publisher permissions are ready.")
