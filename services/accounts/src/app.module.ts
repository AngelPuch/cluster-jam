import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { HealthModule } from './interfaces/http/health/health.module';
import { DatabaseModule } from './infrastructure/database/typeorm.module';

@Module({
    imports: [
        ConfigModule.forRoot({
            isGlobal: true,
        }),
        HealthModule,
        DatabaseModule,
    ],
})
export class AppModule {}
