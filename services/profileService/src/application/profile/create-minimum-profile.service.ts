import { Inject, Injectable } from '@nestjs/common';
import {
    PROFILE_PROVISIONING_PORT,
    type MinimumProfileInput,
    type ProfileProvisioningPort,
    type ProfileProvisioningResult,
} from '../ports/profile-provisioning.port';

@Injectable()
export class CreateMinimumProfileService {
    constructor(
        @Inject(PROFILE_PROVISIONING_PORT)
        private readonly provisioning: ProfileProvisioningPort,
    ) {}

    execute(input: MinimumProfileInput): Promise<ProfileProvisioningResult> {
        return this.provisioning.provision(input);
    }
}
