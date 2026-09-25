import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';

import { environmentValidationSchema } from './infrastructure/config/environment.validation';
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
})
export class AppModule {}
