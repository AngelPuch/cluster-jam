"""Prepare Catalog resources in the existing loopback development broker."""
import base64
import json
import os
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:15672/api"
ADMIN_USER = os.getenv("CATALOG_BROKER_ADMIN_USER", "clusterjam")
ADMIN_PASSWORD = os.environ["CATALOG_BROKER_ADMIN_PASSWORD"]
AUTH = base64.b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()


def call(method, path, body):
    request = Request(
        BASE_URL + path,
        data=json.dumps(body).encode(),
        method=method,
        headers={"Authorization": "Basic " + AUTH, "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        response.read()


for exchange, kind in (("catalog.commands", "topic"), ("catalog.events", "topic"), ("clusterjam.dlx", "direct")):
    call("PUT", "/exchanges/clusterjam/" + exchange, {
        "type": kind, "durable": True, "auto_delete": False, "internal": False, "arguments": {}
    })
for queue in ("catalog.commands.v1", "catalog.commands.v1.dlq", "orders.checkout.v1"):
    call("PUT", "/queues/clusterjam/" + queue, {
        "durable": True, "auto_delete": False, "arguments": {}
    })
call("PUT", "/policies/clusterjam/catalog-reservations-dlq", {
    "pattern": r"^catalog\.commands\.v1$", "apply-to": "queues", "priority": 1,
    "definition": {
        "dead-letter-exchange": "clusterjam.dlx", "dead-letter-routing-key": "catalog.commands.v1"
    }
})
for exchange, queue, key in (
    ("catalog.commands", "catalog.commands.v1", "cmd.catalog.reserve-stock.v1"),
    ("catalog.events", "orders.checkout.v1", "catalog.inventory.reservation-created.v1"),
    ("catalog.events", "orders.checkout.v1", "catalog.inventory.reservation-rejected.v1"),
    ("clusterjam.dlx", "catalog.commands.v1.dlq", "catalog.commands.v1"),
):
    call("POST", f"/bindings/clusterjam/e/{exchange}/q/{queue}", {"routing_key": key, "arguments": {}})

for user, variable, write, read in (
    ("catalog-consumer", "CATALOG_RABBITMQ_PASSWORD", r"^catalog\.events$", r"^catalog\.commands\.v1$"),
    ("orders-test-publisher", "CATALOG_TEST_ORDERS_PASSWORD", r"^catalog\.commands$", "^$"),
):
    call("PUT", "/users/" + user, {"password": os.environ[variable], "tags": ""})
    call("PUT", "/permissions/clusterjam/" + user, {"configure": "^$", "write": write, "read": read})

print("Catalog queue, native DLQ and local runtime/test accounts are ready.")
