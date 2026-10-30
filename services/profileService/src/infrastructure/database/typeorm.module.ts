import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { TypeOrmModule } from '@nestjs/typeorm';
import { createDatabaseOptions } from './typeorm.options';
import { PROFILE_PROVISIONING_PORT } from '../../application/ports/profile-provisioning.port';
import { TypeormProfileProvisioningAdapter } from './repositories/typeorm-profile-provisioning.adapter';

@Module({
    imports: [
        TypeOrmModule.forRootAsync({
            imports: [ConfigModule],
            useFactory: () => ({
                ...createDatabaseOptions(),
                autoLoadEntities: true,
            }),
        }),
    ],
    providers: [
        {
            provide: PROFILE_PROVISIONING_PORT,
            useClass: TypeormProfileProvisioningAdapter,
        },
    ],
    exports: [PROFILE_PROVISIONING_PORT],
})
export class DatabaseModule {}
