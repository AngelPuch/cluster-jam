import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { DataSource } from 'typeorm';
import { DatabaseReadiness } from './database-readiness.service';
import { createDatabaseOptions } from './typeorm.options';

@Module({
    providers: [
        {
            provide: DataSource,
            inject: [ConfigService],
            useFactory: (config: ConfigService) => {
                const input = Object.fromEntries(
                    [
                        'APP_ENV',
                        'HTTP_PORT',
                        'LOG_LEVEL',
                        'DB_HOST',
                        'DB_PORT',
                        'DB_NAME',
                        'DB_USER',
                        'DB_PASSWORD',
                        'DB_SSL',
                        'DB_CA_PATH',
                    ].flatMap((key) => {
                        const value = config.get<unknown>(key);
                        return value === undefined ? [] : [[key, value]];
                    }),
                );
                return new DataSource(createDatabaseOptions(input));
            },
        },
        DatabaseReadiness,
    ],
    exports: [DataSource, DatabaseReadiness],
})
export class DatabaseModule {}
