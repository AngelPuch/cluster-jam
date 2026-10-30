import { Module } from '@nestjs/common';
import { ProfileModule } from '../../../profile.module';
import { SecurityModule } from '../../../infrastructure/security/security.module';
import { ProfilesController } from './profiles.controller';
import { AddressesController } from '../addresses/addresses.controller';
import { JsonContentGuard } from '../common/json-content.guard';

@Module({
    imports: [ProfileModule, SecurityModule],
    controllers: [ProfilesController, AddressesController],
    providers: [JsonContentGuard],
})
export class ProfilesHttpModule {}
