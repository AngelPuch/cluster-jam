import { Test } from '@nestjs/testing';
import { beforeEach, describe, expect, it, jest } from '@jest/globals';

import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
} from '../ports/auth-provider.port';
import {
    PasswordRecoveryError,
    PasswordRecoveryFailure,
} from './errors/password-recovery.error';
import { PasswordRecoveryService } from './password-recovery.service';

describe('PasswordRecoveryService', () => {
    let service: PasswordRecoveryService;
    const requestRecovery =
        jest.fn<AuthProviderPort['requestPasswordRecovery']>();
    const recoverPassword = jest.fn<AuthProviderPort['recoverPassword']>();

    beforeEach(async () => {
        requestRecovery.mockReset().mockResolvedValue(undefined);
        recoverPassword.mockReset().mockResolvedValue(undefined);
        const module = await Test.createTestingModule({
            providers: [
                PasswordRecoveryService,
                {
                    provide: AUTH_PROVIDER_PORT,
                    useValue: {
                        isAvailable: jest.fn(),
                        registerUser: jest.fn(),
                        loginUser: jest.fn(),
                        refreshSession: jest.fn(),
                        requestPasswordRecovery: requestRecovery,
                        recoverPassword,
                    },
                },
            ],
        }).compile();
        service = module.get(PasswordRecoveryService);
    });

    it('requests recovery with only the email address', async () => {
        await expect(
            service.request('user@example.com'),
        ).resolves.toBeUndefined();
        expect(requestRecovery).toHaveBeenCalledWith('user@example.com');
        expect(recoverPassword).not.toHaveBeenCalled();
    });

    it('passes the recovery proof and password unchanged', async () => {
        const input = {
            email: 'user@example.com',
            code: '012345',
            newPassword: ' NewStrongPassword123! ',
        };
        await expect(service.recover(input)).resolves.toBeUndefined();
        expect(recoverPassword).toHaveBeenCalledWith(input);
    });

    it('propagates completion failures instead of reporting success', async () => {
        const error = new PasswordRecoveryError(
            PasswordRecoveryFailure.InvalidRecoveryCode,
        );
        recoverPassword.mockRejectedValue(error);
        await expect(
            service.recover({
                email: 'user@example.com',
                code: '999999',
                newPassword: 'NewStrongPassword123!',
            }),
        ).rejects.toBe(error);
    });
});
