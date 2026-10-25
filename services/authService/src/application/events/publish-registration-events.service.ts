import { Inject, Injectable, Logger } from '@nestjs/common';
import { randomBytes } from 'node:crypto';

import {
  REGISTRATION_OUTBOX_PORT,
  type RegistrationOutboxPort,
} from '../ports/registration-outbox.port';
import {
  REGISTRATION_EVENT_PUBLISHER_PORT,
  type RegistrationEventPublisherPort,
} from '../ports/registration-event-publisher.port';
import { createRegistrationEvent } from './registration-event';

@Injectable()
export class PublishRegistrationEventsService {
  private readonly logger = new Logger(PublishRegistrationEventsService.name);

  constructor(
    @Inject(REGISTRATION_OUTBOX_PORT)
    private readonly outbox: RegistrationOutboxPort,
    @Inject(REGISTRATION_EVENT_PUBLISHER_PORT)
    private readonly publisher: RegistrationEventPublisherPort,
  ) {}

  async execute(
    limit = 10,
    shouldStop: () => boolean = () => false,
  ): Promise<{ published: number; retried: number }> {
    const counts = { published: 0, retried: 0 };
    for (let index = 0; index < limit && !shouldStop(); index += 1) {
      const result = await this.outbox.deliverNext(async (record) => {
        const event = createRegistrationEvent(record);
        const traceparent = `00-${randomBytes(16).toString('hex')}-${randomBytes(8).toString('hex')}-00`;
        await this.publisher.publish(event, traceparent);
      });
      if (result.status === 'empty') break;
      if (result.status === 'published') counts.published += 1;
      else {
        counts.retried += 1;
        this.logger.debug({
          event: 'auth.outbox.delivery.retry',
          code: result.code,
        });
      }
    }
    if (counts.retried > 0) {
      this.logger.warn({
        event: 'auth.outbox.batch.completed',
        ...counts,
      });
    } else if (counts.published > 0) {
      this.logger.log({
        event: 'auth.outbox.batch.completed',
        ...counts,
      });
    }
    return counts;
  }
}
