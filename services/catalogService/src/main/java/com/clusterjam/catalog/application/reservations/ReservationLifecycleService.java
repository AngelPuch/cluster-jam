package com.clusterjam.catalog.application.reservations;

import com.clusterjam.catalog.application.ports.ReservationLifecycleStore;
import com.clusterjam.catalog.application.reservations.ReservationMessages.Command;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationLifecycleService {

    private final ReservationLifecycleStore store;

    public ReservationLifecycleService(ReservationLifecycleStore store) {
        this.store = store;
    }

    @Transactional
    public void transition(Command command) {
        store.transition(command);
    }

    @Transactional
    public boolean expireNext() {
        return store.expireNext();
    }
}
