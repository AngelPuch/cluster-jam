import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { DatabaseReadiness } from '../../../infrastructure/database/database-readiness.service';

@ApiTags('Health')
@Controller('health')
export class HealthController {
    constructor(private readonly database: DatabaseReadiness) {}

    @Get('live')
    @ApiOperation({ summary: 'Check the HTTP process without querying dependencies' })
    @ApiResponse({ status: 200, description: 'Process is responding.' })
    live(): { status: string } {
        return { status: 'ok' };
    }

    @Get('ready')
    @ApiOperation({ summary: 'Check PostgreSQL access; payment processing is not implemented yet' })
    @ApiResponse({ status: 200, description: 'Database is accessible.' })
    @ApiResponse({ status: 503, description: 'Database is unavailable.' })
    async ready(): Promise<{ status: string }> {
        if (!(await this.database.check())) throw new ServiceUnavailableException();
        return { status: 'ok' };
    }
}
