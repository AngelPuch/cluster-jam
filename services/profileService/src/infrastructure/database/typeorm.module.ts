import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AppDataSource } from './typeorm.config';

@Module({
    imports: [
        TypeOrmModule.forRootAsync({
            imports: [ConfigModule],
            useFactory: () => ({
                ...AppDataSource.options,
                autoLoadEntities: true,
            }),
        }),
    ],
})
export class DatabaseModule {}
