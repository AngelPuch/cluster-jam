import { beforeEach, describe, expect, it, jest } from '@jest/globals';

import {
    type CurrentSessionPort,
    CURRENT_SESSION_PORT,
} from '../ports/current-session.port';
import { Test } from '@nestjs/testing';
import { CurrentSessionService } from './current-session.service';

describe('CurrentSessionService', () => {
    let service: CurrentSessionService;
    let provider: jest.Mocked<CurrentSessionPort>;

    beforeEach(async () => {
        provider = {
            getCurrentIdentity: jest.fn(),
            endCurrentSession: jest.fn(),
        };
        const moduleRef = await Test.createTestingModule({
            providers: [
                CurrentSessionService,
                { provide: CURRENT_SESSION_PORT, useValue: provider },
            ],
        }).compile();
        service = moduleRef.get(CurrentSessionService);
    });

    it('returns the identity obtained from the provider', async () => {
        const identity = { userId: 'user-id', email: 'user@example.com' };
        provider.getCurrentIdentity.mockResolvedValue(identity);
        await expect(service.getIdentity('access-token')).resolves.toEqual(
            identity,
        );
        // eslint-disable-next-line @typescript-eslint/unbound-method
        expect(provider.getCurrentIdentity).toHaveBeenCalledWith(
            'access-token',
        );
    });

    it('ends only the supplied session', async () => {
        provider.endCurrentSession.mockResolvedValue();
        await expect(service.end('access-token')).resolves.toBeUndefined();
        // eslint-disable-next-line @typescript-eslint/unbound-method
        expect(provider.endCurrentSession).toHaveBeenCalledWith('access-token');
    });
});
