"""Represent temporary inability to serve an operation."""


class ServiceNotReadyError(Exception):
    """The service's own required infrastructure is unavailable."""
