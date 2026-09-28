import { Test, TestingModule } from '@nestjs/testing';
import { beforeEach, describe, expect, it, jest } from '@jest/globals';

import {
    AUTH_PROVIDER_PORT,
    AuthProviderPort,
} from '../ports/auth-provider.port';
import { ReadinessService } from './readiness.service';

describe('ReadinessService', () => {
    let service: ReadinessService;
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
                ReadinessService,
                {
                    provide: AUTH_PROVIDER_PORT,
                    useValue: authProvider,
                },
            ],
        }).compile();

        service = module.get<ReadinessService>(ReadinessService);
    });

    it('should be ready when the auth provider is available', async () => {
        authProvider.isAvailable.mockResolvedValue(true);

        await expect(service.isReady()).resolves.toBe(true);
    });

    it('should not be ready when the auth provider is unavailable', async () => {
        authProvider.isAvailable.mockResolvedValue(false);

        await expect(service.isReady()).resolves.toBe(false);
    });
});
