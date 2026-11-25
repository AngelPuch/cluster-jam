package com.clusterjam.catalog.application.reservations;

public final class InvalidReservationMessage extends RuntimeException {

    public InvalidReservationMessage() {
        super("Invalid reserve-stock message");
    }
}
