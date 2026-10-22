"""Provision the local development broker only; uses fictitious local credentials."""
import base64
import json
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
print("Local RabbitMQ topology and publisher permissions are ready.")
