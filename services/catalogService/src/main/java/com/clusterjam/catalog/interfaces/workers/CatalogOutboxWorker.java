package com.clusterjam.catalog.interfaces.workers;

import com.clusterjam.catalog.application.outbox.OutboxPublicationFailure;
import com.clusterjam.catalog.application.outbox.OutboxPublicationService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(name = "catalog.outbox.enabled", havingValue = "true")
public class CatalogOutboxWorker {

    private static final Logger LOG = LoggerFactory.getLogger(CatalogOutboxWorker.class);
    private final OutboxPublicationService publications;

    public CatalogOutboxWorker(OutboxPublicationService publications) {
        this.publications = publications;
    }

    @Scheduled(fixedDelay = 5000, initialDelay = 5000)
    public void publish() {
        for (int index = 0; index < 10; index++) {
            try {
                var published = publications.publishNext();
                if (published.isEmpty()) {
                    return;
                }
                // The transactional proxy has committed before publishNext returns to this worker.
                LOG.atInfo().addKeyValue("message_id", published.orElseThrow()).log("catalog_outbox_published");
            } catch (OutboxPublicationFailure pending) {
                LOG.atWarn().addKeyValue("message_id", pending.messageId())
                    .addKeyValue("code", pending.getMessage()).log("catalog_outbox_retry_pending");
                return;
            } catch (RuntimeException databaseOrRowFailure) {
                LOG.warn("catalog_outbox_cycle_failed");
                return;
            }
        }
    }
}
