import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { DataSource } from 'typeorm';
import { RabbitMqListener } from '../../../infrastructure/messaging/rabbitmq-listener';

@Controller('health')
export class HealthController {
    constructor(
        private readonly dataSource: DataSource,
        private readonly broker: RabbitMqListener,
    ) {}

    @Get('live')
    getLiveness() {
        return {
            status: 'ok',
        };
    }

    @Get('ready')
    async getReadiness() {
        if (!this.dataSource.isInitialized || !this.broker.isReady) {
            throw new ServiceUnavailableException();
        }

        try {
            await this.dataSource.query('SELECT 1');
        } catch {
            throw new ServiceUnavailableException();
        }

        return {
            status: 'ok',
        };
    }
}
