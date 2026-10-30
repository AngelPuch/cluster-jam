import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { createDatabaseOptions } from './typeorm.options';
import { PROFILE_PROVISIONING_PORT } from '../../application/ports/profile-provisioning.port';
import { TypeormProfileProvisioningAdapter } from './repositories/typeorm-profile-provisioning.adapter';
import { PROFILE_REPOSITORY_PORT } from '../../application/ports/profile-repository.port';
import { TypeormProfileRepository } from './repositories/typeorm-profile.repository';
import { ADDRESS_BOOK_REPOSITORY_PORT } from '../../application/ports/address-book-repository.port';
import { TypeormAddressBookRepository } from './repositories/typeorm-address-book.repository';

@Module({
    imports: [
        TypeOrmModule.forRootAsync({
            imports: [ConfigModule],
            inject: [ConfigService],
            useFactory: (config: ConfigService) => ({
                // ConfigModule has already resolved mounted secrets. Read its validated
                // values rather than treating Nest's derived process.env as fresh input.
                ...createDatabaseOptions(
                    Object.fromEntries(
                        [
                            'APP_ENV',
                            'HTTP_PORT',
                            'DB_HOST',
                            'DB_PORT',
                            'DB_USER',
                            'DB_PASSWORD',
                            'DB_NAME',
                            'DB_SSL',
                            'DB_CA_PATH',
                        ].flatMap((key) => {
                            const value = config.get<string | number | boolean>(key);
                            return value === undefined ? [] : [[key, String(value)] as const];
                        }),
                    ),
                ),
                autoLoadEntities: true,
                retryAttempts: 3,
                retryDelay: 1000,
            }),
        }),
    ],
    providers: [
        { provide: ADDRESS_BOOK_REPOSITORY_PORT, useClass: TypeormAddressBookRepository },
        { provide: PROFILE_REPOSITORY_PORT, useClass: TypeormProfileRepository },
        {
            provide: PROFILE_PROVISIONING_PORT,
            useClass: TypeormProfileProvisioningAdapter,
        },
    ],
    exports: [PROFILE_PROVISIONING_PORT, PROFILE_REPOSITORY_PORT, ADDRESS_BOOK_REPOSITORY_PORT],
})
export class DatabaseModule {}
