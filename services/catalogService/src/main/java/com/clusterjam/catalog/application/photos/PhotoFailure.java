package com.clusterjam.catalog.application.photos;

public final class PhotoFailure extends RuntimeException {

    public enum Reason {
        INVALID_IMAGE, TOO_LARGE, BUSY, STORAGE_UNAVAILABLE
    }

    private final Reason reason;

    public PhotoFailure(Reason reason) {
        super(reason.name());
        this.reason = reason;
    }

    public Reason reason() {
        return reason;
    }
}
