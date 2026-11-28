import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { readFileSync } from 'node:fs';
import { DataSource } from 'typeorm';
import { DatabaseReadiness } from './database-readiness.service';

@Module({
    providers: [
        {
            provide: DataSource,
            inject: [ConfigService],
            useFactory: (config: ConfigService) => {
                const caPath = config.get<string>('DB_CA_PATH');
                return new DataSource({
                    type: 'postgres',
                    host: config.getOrThrow<string>('DB_HOST'),
                    port: config.getOrThrow<number>('DB_PORT'),
                    database: config.getOrThrow<string>('DB_NAME'),
                    username: config.getOrThrow<string>('DB_USER'),
                    password: config.getOrThrow<string>('DB_PASSWORD'),
                    ssl: config.get<boolean>('DB_SSL')
                        ? { rejectUnauthorized: true, ...(caPath ? { ca: readFileSync(caPath, 'utf8') } : {}) }
                        : false,
                    entities: [],
                    migrations: [],
                    synchronize: false,
                    migrationsRun: false,
                    installExtensions: false,
                    logging: false,
                    poolSize: 5,
                    extra: { connectionTimeoutMillis: 3000, statement_timeout: 3000 },
                });
            },
        },
        DatabaseReadiness,
    ],
    exports: [DatabaseReadiness],
})
export class DatabaseModule {}
