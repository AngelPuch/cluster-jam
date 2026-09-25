import { Controller, Get } from '@nestjs/common';

@Controller('health')
export class HealthController {
    @Get('live')
    getLiveness(): { status: string } {
        return {
            status: 'ok',
        };
    }

    @Get('ready')
    getReadiness(): { status: string } {
        return {
            status: 'ok',
        };
    }
}
