import { Test, TestingModule } from '@nestjs/testing';
import { beforeEach, describe, expect, it, jest } from '@jest/globals';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
} from '../ports/auth-provider.port';
import { AuthLoginError, AuthLoginFailure } from './errors/auth-login.error';
import { LoginUserService } from './login-user.service';

describe('LoginUserService', () => {
    let service: LoginUserService;
    let authProvider: jest.Mocked<AuthProviderPort>;

    beforeEach(async () => {
        authProvider = {
            isAvailable: jest.fn(),
            registerUser: jest.fn(),
            loginUser: jest.fn(),
            refreshSession: jest.fn(),
            requestPasswordRecovery: jest.fn(),
            recoverPassword: jest.fn(),
        };

        const module: TestingModule = await Test.createTestingModule({
            providers: [
                LoginUserService,
                {
                    provide: AUTH_PROVIDER_PORT,
                    useValue: authProvider,
                },
            ],
        }).compile();

        service = module.get<LoginUserService>(LoginUserService);
    });

    it('should login a user through the auth provider', async () => {
        const input = {
            email: 'user@example.com',
            password: 'StrongPassword123!',
        };

        const result = {
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'access-token',
            refreshToken: 'refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        };

        authProvider.loginUser.mockResolvedValue(result);

        await expect(service.execute(input)).resolves.toEqual(result);

        // eslint-disable-next-line @typescript-eslint/unbound-method
        expect(authProvider.loginUser).toHaveBeenCalledWith(input);
    });

    it('should propagate login failures from the auth provider', async () => {
        const error = new AuthLoginError(AuthLoginFailure.InvalidCredentials);

        authProvider.loginUser.mockRejectedValue(error);

        await expect(
            service.execute({
                email: 'user@example.com',
                password: 'WrongPassword!',
            }),
        ).rejects.toBe(error);
    });
});
