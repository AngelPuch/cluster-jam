package com.clusterjam.catalog.application.products;

public final class CatalogProductException extends RuntimeException {

    public enum Reason {
        MISSING, DUPLICATE, INVALID_REFERENCE, INVALID_TRANSITION, STALE
    }

    private final Reason reason;

    public CatalogProductException(Reason reason) {
        super(reason.name());
        this.reason = reason;
    }

    public Reason reason() {
        return reason;
    }
}
