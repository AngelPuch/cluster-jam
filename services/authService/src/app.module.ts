import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { APP_FILTER } from '@nestjs/core';

import { validateEnvironment } from './infrastructure/config/environment.validate';
import { ProblemDetailsFilter } from './interfaces/http/common/errors/problem-details.filter';
import { HealthModule } from './interfaces/http/health/health.module';
import { AuthModule } from './interfaces/http/auth/auth.module';
import { RegistrationEventsModule } from './infrastructure/outbox/registration-events.module';
import { ObservabilityModule } from './infrastructure/observability/observability.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      cache: true,
      validate: validateEnvironment,
    }),
    HealthModule,
    AuthModule,
    RegistrationEventsModule,
    ObservabilityModule,
  ],
  providers: [
    {
      provide: APP_FILTER,
      useClass: ProblemDetailsFilter,
    },
  ],
})
export class AppModule {}
