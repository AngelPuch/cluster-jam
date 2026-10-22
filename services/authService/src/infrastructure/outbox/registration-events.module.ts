import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { connect } from 'amqplib';

import { PublishRegistrationEventsService } from '../../application/events/publish-registration-events.service';
import { REGISTRATION_OUTBOX_PORT } from '../../application/ports/registration-outbox.port';
import { REGISTRATION_EVENT_PUBLISHER_PORT } from '../../application/ports/registration-event-publisher.port';
import { RegistrationOutboxWorker } from '../../interfaces/workers/registration-outbox.worker';
import {
    AMQP_CONNECTOR,
    RabbitMqRegistrationEventPublisher,
} from '../messaging/rabbitmq-registration-event.publisher';
import {
    OUTBOX_DATABASE,
    createOutboxDatabase,
} from './outbox-database.provider';
import { PostgresRegistrationOutboxAdapter } from './postgres-registration-outbox.adapter';

@Module({
    providers: [
        { provide: AMQP_CONNECTOR, useValue: { connect } },
        {
            provide: OUTBOX_DATABASE,
            inject: [ConfigService],
            useFactory: createOutboxDatabase,
        },
        PostgresRegistrationOutboxAdapter,
        {
            provide: REGISTRATION_OUTBOX_PORT,
            useExisting: PostgresRegistrationOutboxAdapter,
        },
        RabbitMqRegistrationEventPublisher,
        {
            provide: REGISTRATION_EVENT_PUBLISHER_PORT,
            useExisting: RabbitMqRegistrationEventPublisher,
        },
        PublishRegistrationEventsService,
        RegistrationOutboxWorker,
    ],
    exports: [PublishRegistrationEventsService],
})
export class RegistrationEventsModule {}
