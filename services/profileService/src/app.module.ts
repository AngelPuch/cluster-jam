import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { HealthModule } from './interfaces/http/health/health.module';
import { ProfileModule } from './profile.module';
import { validateEnvironment } from './infrastructure/config/environment.validation';

@Module({
    imports: [
        ConfigModule.forRoot({
            isGlobal: true,
            validate: validateEnvironment,
        }),
        HealthModule,
        ProfileModule,
    ],
})
export class AppModule {}
