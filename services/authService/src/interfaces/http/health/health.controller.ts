import { Controller, Get, ServiceUnavailableException } from '@nestjs/common';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

import { ReadinessService } from '../../../application/health/readiness.service';
import { HealthResponseDto } from './dto/health-response.dto';

@ApiTags('Health')
@Controller('health')
export class HealthController {
    constructor(private readonly readinessService: ReadinessService) {}

    @Get('live')
    @ApiOperation({
        summary: 'Check service liveness',
        description: 'Confirms that the Auth Service process is running.',
    })
    @ApiOkResponse({
        description: 'The Auth Service process is alive.',
        type: HealthResponseDto,
    })
    getLiveness(): HealthResponseDto {
        return {
            status: 'ok',
        };
    }

    @Get('ready')
    @ApiOperation({
        summary: 'Check service readiness',
        description:
            'Confirms that the Auth Service can reach Supabase Auth and is ready to receive authentication requests.',
    })
    @ApiOkResponse({
        description: 'The Auth Service is ready.',
        type: HealthResponseDto,
    })
    async getReadiness(): Promise<HealthResponseDto> {
        const isReady = await this.readinessService.isReady();

        if (!isReady) {
            throw new ServiceUnavailableException();
        }

        return {
            status: 'ok',
        };
    }
}
