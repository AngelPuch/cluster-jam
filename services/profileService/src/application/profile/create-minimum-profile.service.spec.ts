import { CreateMinimumProfileService } from './create-minimum-profile.service';
import type { ProfileProvisioningPort } from '../ports/profile-provisioning.port';
import { jest } from '@jest/globals';

describe('CreateMinimumProfileService', () => {
    const input = { eventId: 'event', userId: 'user', initialContactEmail: 'customer@example.com' };

    it.each([{ status: 'processed', profileCreated: true }, { status: 'duplicate' }] as const)(
        'returns the persistence outcome after completion: %j',
        async (result) => {
            const provision = jest.fn<ProfileProvisioningPort['provision']>().mockResolvedValue(result);
            const service = new CreateMinimumProfileService({ provision });
            await expect(service.execute(input)).resolves.toEqual(result);
            expect(provision).toHaveBeenCalledWith(input);
        },
    );

    it('propagates a failure so the consumer cannot acknowledge it as processed', async () => {
        const error = new Error('Persistence unavailable');
        const port: ProfileProvisioningPort = { provision: () => Promise.reject(error) };
        await expect(new CreateMinimumProfileService(port).execute(input)).rejects.toBe(error);
    });
});
