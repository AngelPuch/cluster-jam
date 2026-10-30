import { Module } from '@nestjs/common';
import { CreateMinimumProfileService } from './application/profile/create-minimum-profile.service';
import { DatabaseModule } from './infrastructure/database/typeorm.module';
import { GetMyProfileService } from './application/profile/get-my-profile.service';
import { CompleteOnboardingService } from './application/profile/complete-onboarding.service';
import { GetMyAddressesService } from './application/addresses/get-my-addresses.service';
import { ManageMyAddressesService } from './application/addresses/manage-my-addresses.service';

@Module({
    imports: [DatabaseModule],
    providers: [
        CreateMinimumProfileService,
        GetMyProfileService,
        CompleteOnboardingService,
        GetMyAddressesService,
        ManageMyAddressesService,
    ],
    exports: [
        CreateMinimumProfileService,
        GetMyProfileService,
        CompleteOnboardingService,
        GetMyAddressesService,
        ManageMyAddressesService,
    ],
})
export class ProfileModule {}
