import { Inject, Injectable } from '@nestjs/common';
import { PROFILE_REPOSITORY_PORT, type ProfileRepositoryPort } from '../ports/profile-repository.port';
import type { CustomerProfile } from './profile';
import { ProfileError, ProfileFailure } from './profile.error';

@Injectable()
export class GetMyProfileService {
    constructor(@Inject(PROFILE_REPOSITORY_PORT) private readonly profiles: ProfileRepositoryPort) {}

    async execute(userId: string): Promise<CustomerProfile> {
        const profile = await this.profiles.findByUserId(userId);
        if (!profile) throw new ProfileError(ProfileFailure.NotReady);
        return profile;
    }
}
