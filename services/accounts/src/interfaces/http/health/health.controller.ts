import { Controller, Get } from '@nestjs/common';

@Controller('health')
export class HealthController {
    @Get('live')
    getLiveness() {
        return {
            status: 'ok',
        };
    }
}
