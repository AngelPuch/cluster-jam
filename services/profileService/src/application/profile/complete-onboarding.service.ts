import { Inject, Injectable } from '@nestjs/common';
import { PROFILE_REPOSITORY_PORT, type ProfileRepositoryPort } from '../ports/profile-repository.port';
import type { CustomerProfile, UpdateProfileInput } from './profile';
import { ProfileError, ProfileFailure } from './profile.error';
import { completeProfile, normalizeProfileUpdate } from './profile-rules';

@Injectable()
export class CompleteOnboardingService {
    constructor(@Inject(PROFILE_REPOSITORY_PORT) private readonly profiles: ProfileRepositoryPort) {}

    async execute(userId: string, input: UpdateProfileInput, expectedRevision: string): Promise<CustomerProfile> {
        const update = normalizeProfileUpdate(input);
        const profile = await this.profiles.update(userId, (current) => {
            if (current.revision !== expectedRevision) throw new ProfileError(ProfileFailure.RevisionMismatch);
            return completeProfile(current, update);
        });
        if (!profile) throw new ProfileError(ProfileFailure.NotReady);
        return profile;
    }
}
