import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { DataSource } from 'typeorm';
import { RabbitMqListener } from '../../../infrastructure/messaging/rabbitmq-listener';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { profileProblemResponses } from '../openapi/problem-responses';

@ApiTags('Health')
@Controller('health')
export class HealthController {
    constructor(
        private readonly dataSource: DataSource,
        private readonly broker: RabbitMqListener,
    ) {}

    @Get('live')
    @ApiOperation({ summary: 'Process liveness; no authentication or dependency checks' })
    @ApiResponse({
        status: 200,
        schema: { type: 'object', required: ['status'], properties: { status: { type: 'string', enum: ['ok'] } } },
    })
    getLiveness() {
        return {
            status: 'ok',
        };
    }

    @Get('ready')
    @ApiOperation({ summary: 'Readiness of PostgreSQL and the configured registration consumer' })
    @ApiResponse({
        status: 200,
        schema: { type: 'object', required: ['status'], properties: { status: { type: 'string', enum: ['ok'] } } },
    })
    @ApiResponse(profileProblemResponses[503])
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
