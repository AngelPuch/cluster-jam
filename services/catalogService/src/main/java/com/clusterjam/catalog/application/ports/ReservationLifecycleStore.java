package com.clusterjam.catalog.application.ports;

import com.clusterjam.catalog.application.reservations.ReservationMessages.Command;

public interface ReservationLifecycleStore {

    void transition(Command command);

    boolean expireNext();
}
