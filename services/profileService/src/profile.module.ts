import { Module } from '@nestjs/common';
import { CreateMinimumProfileService } from './application/profile/create-minimum-profile.service';
import { DatabaseModule } from './infrastructure/database/typeorm.module';

@Module({
    imports: [DatabaseModule],
    providers: [CreateMinimumProfileService],
    exports: [CreateMinimumProfileService],
})
export class ProfileModule {}
