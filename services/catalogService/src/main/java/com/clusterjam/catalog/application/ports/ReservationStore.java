package com.clusterjam.catalog.application.ports;

import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;

public interface ReservationStore {

    void reserve(ReserveCommand command);
}
