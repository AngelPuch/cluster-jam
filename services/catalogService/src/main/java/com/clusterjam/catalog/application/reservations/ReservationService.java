package com.clusterjam.catalog.application.reservations;

import com.clusterjam.catalog.application.ports.ReservationStore;
import com.clusterjam.catalog.application.reservations.ReservationMessages.ReserveCommand;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationService {

    private final ReservationStore store;

    public ReservationService(ReservationStore store) {
        this.store = store;
    }

    @Transactional
    public void reserve(ReserveCommand command) {
        store.reserve(command);
    }
}
