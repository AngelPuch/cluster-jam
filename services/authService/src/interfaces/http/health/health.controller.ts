import { Controller, Get } from '@nestjs/common';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

import { HealthResponseDto } from './dto/health-response.dto';

@ApiTags('Health')
@Controller('health')
export class HealthController {
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
            'Confirms that the Auth Service is ready to receive requests.',
    })
    @ApiOkResponse({
        description: 'The Auth Service is ready.',
        type: HealthResponseDto,
    })
    getReadiness(): HealthResponseDto {
        return {
            status: 'ok',
        };
    }
}
