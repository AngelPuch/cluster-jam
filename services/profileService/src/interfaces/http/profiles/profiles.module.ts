import { Module } from '@nestjs/common';
import { ProfileModule } from '../../../profile.module';
import { SecurityModule } from '../../../infrastructure/security/security.module';
import { ProfilesController } from './profiles.controller';

@Module({ imports: [ProfileModule, SecurityModule], controllers: [ProfilesController] })
export class ProfilesHttpModule {}
