import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { DataSource } from 'typeorm';

@Controller('health')
export class HealthController {
    constructor(private readonly dataSource: DataSource) {}

    @Get('live')
    getLiveness() {
        return {
            status: 'ok',
        };
    }

    @Get('ready')
    async getReadiness() {
        if (!this.dataSource.isInitialized) {
            throw new ServiceUnavailableException();
        }

        await this.dataSource.query('SELECT 1');

        return {
            status: 'ok',
        };
    }
}
