package com.clusterjam.catalog.application.inventory;

public final class InventoryFailure extends RuntimeException {

    public enum Reason {
        MISSING, INVALID, CONFLICT
    }

    private final Reason reason;

    public InventoryFailure(Reason reason) {
        super(reason.name());
        this.reason = reason;
    }

    public Reason reason() {
        return reason;
    }
}
