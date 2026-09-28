import { Test, TestingModule } from '@nestjs/testing';
import { beforeEach, describe, expect, it, jest } from '@jest/globals';

import {
    AuthRegistrationError,
    AuthRegistrationFailure,
} from './errors/auth-registration.error';
import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    UserRegistrationStatus,
} from '../ports/auth-provider.port';
import { RegisterUserService } from './register-user.service';

describe('RegisterUserService', () => {
    let service: RegisterUserService;
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
                RegisterUserService,
                {
                    provide: AUTH_PROVIDER_PORT,
                    useValue: authProvider,
                },
            ],
        }).compile();

        service = module.get<RegisterUserService>(RegisterUserService);
    });

    it('should register a user through the auth provider', async () => {
        const input = {
            email: 'user@example.com',
            password: 'StrongPassword123!',
        };

        const result = {
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            status: UserRegistrationStatus.PendingEmailConfirmation,
        };

        authProvider.registerUser.mockResolvedValue(result);

        await expect(service.execute(input)).resolves.toEqual(result);

        // eslint-disable-next-line @typescript-eslint/unbound-method
        expect(authProvider.registerUser).toHaveBeenCalledWith(input);
    });

    it('should propagate registration failures from the auth provider', async () => {
        const error = new AuthRegistrationError(
            AuthRegistrationFailure.EmailAlreadyRegistered,
        );

        authProvider.registerUser.mockRejectedValue(error);

        await expect(
            service.execute({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            }),
        ).rejects.toBe(error);
    });
});
