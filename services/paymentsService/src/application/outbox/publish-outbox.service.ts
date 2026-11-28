import { Inject, Injectable } from '@nestjs/common';
import {
    OUTBOX_STORE,
    PAYMENT_EVENT_PUBLISHER,
    type OutboxStore,
    type PaymentEventPublisher,
} from '../ports/outbox.port';

@Injectable()
export class PublishOutboxService {
    constructor(
        @Inject(OUTBOX_STORE) private readonly store: OutboxStore,
        @Inject(PAYMENT_EVENT_PUBLISHER) private readonly publisher: PaymentEventPublisher,
    ) {}

    async runBatch(): Promise<void> {
        for (let count = 0; count < 10; count++) {
            if (!(await this.store.publishNext((event) => this.publisher.publish(event)))) break;
        }
    }
}
