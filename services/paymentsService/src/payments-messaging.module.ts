import { Module } from '@nestjs/common';
import { PublishOutboxService } from './application/outbox/publish-outbox.service';
import { OUTBOX_STORE, PAYMENT_EVENT_PUBLISHER } from './application/ports/outbox.port';
import { DatabaseModule } from './infrastructure/database/database.module';
import { TypeormOutboxStore } from './infrastructure/database/typeorm-outbox.store';
import { PaymentBroker } from './infrastructure/messaging/payment-broker';
import { ObservabilityModule } from './infrastructure/observability/observability.module';
import { PaymentCommandConsumer } from './interfaces/messaging/payment-command.consumer';
import { PaymentsMessagingWorker } from './interfaces/workers/payments-messaging.worker';
import { PaymentsModule } from './payments.module';

@Module({
    imports: [DatabaseModule, ObservabilityModule, PaymentsModule],
    providers: [
        PaymentBroker,
        PaymentCommandConsumer,
        PaymentsMessagingWorker,
        PublishOutboxService,
        { provide: OUTBOX_STORE, useClass: TypeormOutboxStore },
        { provide: PAYMENT_EVENT_PUBLISHER, useExisting: PaymentBroker },
    ],
})
export class PaymentsMessagingModule {}
