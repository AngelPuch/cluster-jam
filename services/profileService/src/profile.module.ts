import { Module } from '@nestjs/common';
import { CreateMinimumProfileService } from './application/profile/create-minimum-profile.service';
import { DatabaseModule } from './infrastructure/database/typeorm.module';
import { GetMyProfileService } from './application/profile/get-my-profile.service';
import { CompleteOnboardingService } from './application/profile/complete-onboarding.service';

@Module({
    imports: [DatabaseModule],
    providers: [CreateMinimumProfileService, GetMyProfileService, CompleteOnboardingService],
    exports: [CreateMinimumProfileService, GetMyProfileService, CompleteOnboardingService],
})
export class ProfileModule {}
