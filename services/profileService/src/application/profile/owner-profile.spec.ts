import { jest } from '@jest/globals';
import { GetMyProfileService } from './get-my-profile.service';
import { CompleteOnboardingService } from './complete-onboarding.service';
import type { ProfileRepositoryPort } from '../ports/profile-repository.port';
import type { CustomerProfile } from './profile';
import { ProfileError, ProfileFailure } from './profile.error';

describe('Owner profile use cases', () => {
    const current: CustomerProfile = {
        userId: 'owner',
        fullName: null,
        phone: null,
        contactEmail: 'initial@example.com',
        onboardingStatus: 'PENDING',
        createdAt: new Date(),
        updatedAt: new Date(),
        revision: 'a'.repeat(64),
    };
    const findByUserId = jest.fn<ProfileRepositoryPort['findByUserId']>();
    const update = jest.fn<ProfileRepositoryPort['update']>();
    const port: ProfileRepositoryPort = { findByUserId, update };
    beforeEach(() => {
        findByUserId.mockReset();
        update.mockReset();
    });

    it('reads only the supplied verified owner and never provisions on absence', async () => {
        findByUserId.mockResolvedValueOnce(current).mockResolvedValueOnce(null);
        await expect(new GetMyProfileService(port).execute('owner')).resolves.toBe(current);
        expect(findByUserId).toHaveBeenCalledWith('owner');
        await expect(new GetMyProfileService(port).execute('missing')).rejects.toThrow(
            new ProfileError(ProfileFailure.NotReady),
        );
        expect(update).not.toHaveBeenCalled();
    });

    it('normalizes before persistence and checks revision inside the repository callback', async () => {
        update.mockImplementation((userId, change) => {
            expect(userId).toBe('owner');
            return Promise.resolve({ ...current, ...change(current), revision: 'b'.repeat(64) });
        });
        await expect(
            new CompleteOnboardingService(port).execute('owner', { fullName: ' María ' }, current.revision),
        ).resolves.toMatchObject({ fullName: 'María', onboardingStatus: 'PENDING', revision: 'b'.repeat(64) });
        await expect(
            new CompleteOnboardingService(port).execute('owner', { fullName: 'Other' }, 'stale'),
        ).rejects.toThrow(new ProfileError(ProfileFailure.RevisionMismatch));
    });

    it('rejects invalid input before storage and never creates missing profiles on PATCH', async () => {
        const useCase = new CompleteOnboardingService(port);
        await expect(useCase.execute('owner', {}, current.revision)).rejects.toThrow(ProfileError);
        expect(update).not.toHaveBeenCalled();
        update.mockResolvedValue(null);
        await expect(useCase.execute('missing', { fullName: 'María' }, current.revision)).rejects.toThrow(
            new ProfileError(ProfileFailure.NotReady),
        );
    });
});
