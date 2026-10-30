import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { HealthModule } from './interfaces/http/health/health.module';
import { ObservabilityModule } from './infrastructure/observability/observability.module';
import { validateEnvironment } from './infrastructure/config/environment.validation';

@Module({
    imports: [
        ConfigModule.forRoot({
            isGlobal: true,
            validate: validateEnvironment,
        }),
        ObservabilityModule,
        HealthModule,
    ],
})
export class AppModule {}
