import { Module } from '@nestjs/common';
import { connect } from 'amqplib';
import { ProfileModule } from '../../profile.module';
import { UserRegisteredConsumer } from '../../interfaces/messaging/user-registered.consumer';
import { ObservabilityModule } from '../observability/observability.module';
import { AMQP_CONNECTOR, RabbitMqListener } from './rabbitmq-listener';

@Module({
    imports: [ProfileModule, ObservabilityModule],
    providers: [{ provide: AMQP_CONNECTOR, useValue: { connect } }, UserRegisteredConsumer, RabbitMqListener],
    exports: [RabbitMqListener],
})
export class RabbitMqModule {}
