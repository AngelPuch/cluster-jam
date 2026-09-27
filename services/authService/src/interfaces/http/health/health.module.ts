import { Module } from '@nestjs/common';

import { ReadinessService } from '../../../application/health/readiness.service';
import { SupabaseModule } from '../../../infrastructure/supabase/supabase.module';
import { HealthController } from './health.controller';

@Module({
    imports: [SupabaseModule],
    controllers: [HealthController],
    providers: [ReadinessService],
})
export class HealthModule {}
