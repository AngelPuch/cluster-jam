"""Inspect health without restarting or changing components."""

from .bundles import storage_client
from .runtime import ComposeContext, OperationError, psql, revision, run


def service_running(command: list[str], service: str) -> bool:
    try:
        return bool(
            run(
                [*command, "ps", "--status", "running", "--quiet", service],
                timeout=15,
            ).strip()
        )
    except OperationError:
        return False


def http_ready(context: ComposeContext, endpoint: str) -> bool:
    script = (
        "import urllib.request; "
        "urllib.request.urlopen('http://127.0.0.1:8080/health/"
        + endpoint
        + "', timeout=5).close()"
    )
    try:
        run(
            [
                *context.command,
                "exec",
                "-T",
                "personalization",
                "python",
                "-c",
                script,
            ],
            timeout=15,
        )
        return True
    except OperationError:
        return False


def inspect_status(
    context: ComposeContext,
    *,
    require_worker: bool = False,
    require_rpc: bool = False,
    require_https: bool = False,
) -> tuple[bool, dict[str, str]]:
    checks: dict[str, str] = {}
    checks["rest_liveness"] = "ok" if http_ready(context, "live") else "failed"
    checks["rest_readiness"] = (
        "ok" if http_ready(context, "ready") else "failed"
    )
    try:
        result = psql(
            context.database_id(),
            "SELECT json_build_object('revision',"
            "(SELECT version_num FROM app.alembic_version),'pending_files',"
            "(SELECT count(*) FROM app.archivo "
            "WHERE estado='PENDIENTE_CARGA'))",
        )
        checks["database_revision"] = (
            "ok" if result.get("revision") == revision() else "failed"
        )
        pending = result.get("pending_files")
        if isinstance(pending, int) and not isinstance(pending, bool):
            checks["pending_files"] = str(pending)
    except OperationError:
        checks["database_revision"] = "failed"
    try:
        storage_client(context).ensure_private()
        checks["storage_bucket"] = "ok"
    except OperationError:
        checks["storage_bucket"] = "failed"
    modules = {
        "personalization-worker": "personalization.interfaces.workers.health",
        "personalization-grpc": "personalization.interfaces.grpc.health",
    }
    required = {
        "personalization-worker": require_worker,
        "personalization-grpc": require_rpc,
    }
    for service, module in modules.items():
        if not service_running(context.command, service):
            checks[service] = (
                "failed" if required[service] else "not_running_optional"
            )
            continue
        try:
            run(
                [
                    *context.command,
                    "exec",
                    "-T",
                    service,
                    "python",
                    "-m",
                    module,
                ],
                timeout=15,
            )
            checks[service] = "ok"
        except OperationError:
            checks[service] = "failed"
    if service_running(context.gateway, "nginx"):
        hostname = "clusterjam.test" if context.deployment else "localhost"
        try:
            run(
                [
                    *context.gateway,
                    "exec",
                    "-T",
                    "nginx",
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "5",
                    "--cacert",
                    "/run/config/cluster-ca.crt",
                    "--resolve",
                    f"{hostname}:8443:127.0.0.1",
                    f"https://{hostname}:8443/health/personalization/ready",
                ],
                timeout=15,
            )
            checks["https_readiness"] = "ok"
        except OperationError:
            checks["https_readiness"] = "failed"
    else:
        checks["https_readiness"] = (
            "failed" if require_https else "not_running_optional"
        )
    return "failed" not in checks.values(), checks
