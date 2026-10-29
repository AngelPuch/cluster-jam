"""Check only the local TLS listener; database readiness is separate."""

import os
import socket
import ssl


def main() -> int:
    try:
        context = ssl.create_default_context(
            cafile=os.environ["GRPC_HEALTH_CA_FILE"]
        )
        context.set_alpn_protocols(["h2"])
        with socket.create_connection(
            ("127.0.0.1", int(os.environ["GRPC_PORT"])), timeout=2
        ) as stream:
            with context.wrap_socket(
                stream, server_hostname="personalization-grpc"
            ) as secured:
                return 0 if secured.selected_alpn_protocol() == "h2" else 1
    except OSError, ValueError, KeyError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
