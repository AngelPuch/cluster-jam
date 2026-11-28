import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_FILTER } from '@nestjs/core';
import { validateEnvironment } from './infrastructure/config/environment.validation';
import { DatabaseModule } from './infrastructure/database/database.module';
import { ObservabilityModule } from './infrastructure/observability/observability.module';
import { HealthController } from './interfaces/http/health/health.controller';
import { ProblemDetailsFilter } from './interfaces/http/common/problem-details.filter';

@Module({
    imports: [
        ConfigModule.forRoot({ isGlobal: true, validate: validateEnvironment }),
        ObservabilityModule,
        DatabaseModule,
    ],
    controllers: [HealthController],
    providers: [{ provide: APP_FILTER, useClass: ProblemDetailsFilter }],
})
export class AppModule {}
