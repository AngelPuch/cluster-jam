import { readFileSync } from 'node:fs';
import type { DataSourceOptions } from 'typeorm';
import { validateEnvironment } from '../config/environment.validation';
import { AddressEntity } from './entities/address.entity';
import { ProfileEntity } from './entities/profile.entity';
import { InboxMessageEntity } from './entities/inbox-message.entity';
import { CreateAccounts1789608835902 } from './migrations/1789608835902-create-accounts';
import { UpdateProfile1789964255801 } from './migrations/1789964255801-update-profile';
import { AddInboxAndOnboardingStatus1793232000000 } from './migrations/1793232000000-add-inbox-and-onboarding-status';

export function createDatabaseOptions(environment: NodeJS.ProcessEnv = process.env): DataSourceOptions {
    const config = validateEnvironment(environment);
    return {
        type: 'postgres',
        host: String(config.DB_HOST),
        port: Number(config.DB_PORT),
        username: String(config.DB_USER),
        password: String(config.DB_PASSWORD),
        database: String(config.DB_NAME),
        ssl: config.DB_SSL
            ? {
                  rejectUnauthorized: true,
                  ...(environment.DB_CA_PATH ? { ca: readFileSync(environment.DB_CA_PATH, 'utf8') } : {}),
              }
            : false,
        entities: [ProfileEntity, AddressEntity, InboxMessageEntity],
        migrations: [CreateAccounts1789608835902, UpdateProfile1789964255801, AddInboxAndOnboardingStatus1793232000000],
        synchronize: false,
        migrationsRun: false,
        installExtensions: false,
        migrationsTransactionMode: 'all',
        logging: false,
        poolSize: 10,
        extra: {
            connectionTimeoutMillis: 3000,
            statement_timeout: 8000,
            idle_in_transaction_session_timeout: 10000,
        },
    };
}
