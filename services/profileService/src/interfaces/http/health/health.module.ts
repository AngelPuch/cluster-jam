import { Module } from '@nestjs/common';
import { HealthController } from './health.controller';
import { RabbitMqModule } from '../../../infrastructure/messaging/rabbitmq.module';

@Module({
    imports: [RabbitMqModule],
    controllers: [HealthController],
})
export class HealthModule {}
