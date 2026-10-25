"""Test readiness policy independently of HTTP and database adapters."""

import pytest

from personalization.application.errors.service_not_ready_error import (
    ServiceNotReadyError,
)
from personalization.application.health.readiness_service import (
    ReadinessService,
)


@pytest.mark.parametrize("ready", [True, False])
def test_readiness_policy(ready: bool) -> None:
    class ReadinessStub:
        def is_ready(self) -> bool:
            return ready

    service = ReadinessService(ReadinessStub())
    if ready:
        service.ensure_ready()
    else:
        with pytest.raises(ServiceNotReadyError):
            service.ensure_ready()
