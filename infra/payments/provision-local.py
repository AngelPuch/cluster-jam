"""Prepare Payments resources in the existing loopback development broker."""
import base64
import json
import os
from urllib.request import Request, urlopen


def main():
    admin = os.getenv("PAYMENTS_BROKER_ADMIN_USER", "clusterjam")
    password = os.environ["PAYMENTS_BROKER_ADMIN_PASSWORD"]
    auth = base64.b64encode(f"{admin}:{password}".encode()).decode()

    def call(method, path, body):
        request = Request("http://127.0.0.1:15672/api" + path,
                          data=json.dumps(body).encode(), method=method,
                          headers={"Authorization": "Basic " + auth, "Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:
            response.read()

    for exchange, kind in (("payments.commands", "topic"), ("payments.events", "topic"), ("clusterjam.dlx", "direct")):
        call("PUT", "/exchanges/clusterjam/" + exchange, {
            "type": kind, "durable": True, "auto_delete": False, "internal": False, "arguments": {}
        })
    for queue in ("payments.commands.v1", "payments.commands.v1.dlq", "orders.checkout.v1"):
        call("PUT", "/queues/clusterjam/" + queue, {
            "durable": True, "auto_delete": False, "arguments": {}
        })
    call("PUT", "/policies/clusterjam/payments-commands-dlq", {
        "pattern": r"^payments\.commands\.v1$", "apply-to": "queues", "priority": 1,
        "definition": {"dead-letter-exchange": "clusterjam.dlx", "dead-letter-routing-key": "payments.commands.v1"}
    })
    for routing_key in ("enable-payment", "cancel-payment", "refund-full"):
        call("POST", "/bindings/clusterjam/e/payments.commands/q/payments.commands.v1", {
            "routing_key": f"cmd.payments.{routing_key}.v1", "arguments": {}
        })
    for routing_key in ("payments.payment.enabled.v1", "payments.payment.succeeded.v1",
                        "payments.payment.not-completed.v1", "payments.refund.succeeded.v1"):
        call("POST", "/bindings/clusterjam/e/payments.events/q/orders.checkout.v1", {
            "routing_key": routing_key, "arguments": {}
        })
    call("POST", "/bindings/clusterjam/e/clusterjam.dlx/q/payments.commands.v1.dlq", {
        "routing_key": "payments.commands.v1", "arguments": {}
    })
    call("PUT", "/users/payments-consumer", {"password": os.environ["PAYMENTS_RABBITMQ_PASSWORD"], "tags": ""})
    call("PUT", "/permissions/clusterjam/payments-consumer", {
        "configure": "^$", "write": r"^payments\.events$", "read": r"^payments\.commands\.v1$"
    })
    print("Payments command queue, native DLQ and local runtime account are ready.")


if __name__ == "__main__":
    main()
