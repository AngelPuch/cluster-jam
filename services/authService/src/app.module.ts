import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_FILTER } from '@nestjs/core';

import { environmentValidationSchema } from './infrastructure/config/environment.validation';
import { ProblemDetailsFilter } from './interfaces/http/common/errors/problem-details.filter';
import { HealthModule } from './interfaces/http/health/health.module';

@Module({
    imports: [
        ConfigModule.forRoot({
            isGlobal: true,
            cache: true,
            validationSchema: environmentValidationSchema,
        }),
        HealthModule,
    ],
    providers: [
        {
            provide: APP_FILTER,
            useClass: ProblemDetailsFilter,
        },
    ],
})
export class AppModule {}
