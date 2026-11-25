package com.clusterjam.catalog.interfaces.workers;

import com.clusterjam.catalog.application.reservations.ReservationLifecycleService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "catalog.reservations.expiration-enabled", havingValue = "true", matchIfMissing = true)
public class ReservationExpirationWorker {

    private static final Logger LOG = LoggerFactory.getLogger(ReservationExpirationWorker.class);
    private final ReservationLifecycleService lifecycle;

    public ReservationExpirationWorker(ReservationLifecycleService lifecycle) {
        this.lifecycle = lifecycle;
    }

    @Scheduled(fixedDelay = 30000, initialDelay = 30000)
    public void expire() {
        for (int index = 0; index < 10; index++) {
            try {
                if (!lifecycle.expireNext()) {
                    return;
                }
            } catch (RuntimeException technical) {
                LOG.warn("catalog_reservation_expiration_failed");
                return;
            }
        }
    }
}
