import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Test, TestingModule } from '@nestjs/testing';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
} from '../ports/auth-provider.port';
import {
    AuthRefreshError,
    AuthRefreshFailure,
} from './errors/auth-refresh.error';
import { RefreshSessionService } from './refresh-session.service';

describe('RefreshSessionService', () => {
    let service: RefreshSessionService;
    let authProvider: jest.Mocked<AuthProviderPort>;

    beforeEach(async () => {
        authProvider = {
            isAvailable: jest.fn(),
            registerUser: jest.fn(),
            loginUser: jest.fn(),
            refreshSession: jest.fn(),
        };

        const module: TestingModule = await Test.createTestingModule({
            providers: [
                RefreshSessionService,
                {
                    provide: AUTH_PROVIDER_PORT,
                    useValue: authProvider,
                },
            ],
        }).compile();

        service = module.get<RefreshSessionService>(RefreshSessionService);
    });

    it('renews a session through the provider', async () => {
        const input = { refreshToken: 'old-refresh-token' };
        const result = {
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'new-access-token',
            refreshToken: 'new-refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        };

        authProvider.refreshSession.mockResolvedValue(result);

        await expect(service.execute(input)).resolves.toEqual(result);

        // eslint-disable-next-line @typescript-eslint/unbound-method
        expect(authProvider.refreshSession).toHaveBeenCalledWith(input);
    });

    it('propagates a provider failure', async () => {
        const error = new AuthRefreshError(
            AuthRefreshFailure.InvalidRefreshToken,
        );

        authProvider.refreshSession.mockRejectedValue(error);

        await expect(
            service.execute({ refreshToken: 'invalid-token' }),
        ).rejects.toBe(error);
    });
});
