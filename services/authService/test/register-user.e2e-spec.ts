import { INestApplication } from '@nestjs/common';
import {
    afterAll,
    beforeAll,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';
import request from 'supertest';
import { App } from 'supertest/types';

import {
    AuthRegistrationError,
    AuthRegistrationFailure,
} from '../src/application/auth/errors/auth-registration.error';
import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    UserRegistrationStatus,
} from '../src/application/ports/auth-provider.port';
import { createTestApp } from './helpers/create-test-app';
import { ProblemResponse } from './helpers/problem-response';

describe('User registration API (e2e)', () => {
    let app: INestApplication<App>;
    let registerUserSpy: jest.SpiedFunction<AuthProviderPort['registerUser']>;

    beforeAll(async () => {
        app = await createTestApp();
        const provider = app.get<AuthProviderPort>(AUTH_PROVIDER_PORT);
        registerUserSpy = jest.spyOn(provider, 'registerUser');
    });

    beforeEach(() => {
        registerUserSpy.mockReset();
    });

    it('POST /api/v1/registrations should register a user pending email confirmation', async () => {
        registerUserSpy.mockResolvedValue({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            status: UserRegistrationStatus.PendingEmailConfirmation,
        });

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(201);

        expect(response.body).toEqual({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            status: 'PENDING_EMAIL_CONFIRMATION',
        });

        expect(registerUserSpy).toHaveBeenCalledWith({
            email: 'user@example.com',
            password: 'StrongPassword123!',
        });
    });

    it('POST /api/v1/registrations should reject invalid fields and role assignment', async () => {
        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'not-an-email',
                password: 'short',
                role: 'administrator',
            })
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);

        const body = response.body as ProblemResponse;

        expect(body.code).toBe('VALIDATION_ERROR');

        expect(body.errors).toEqual(
            expect.arrayContaining([
                'email must be an email',
                'password must be longer than or equal to 8 characters',
                'property role should not exist',
            ]),
        );

        expect(registerUserSpy).not.toHaveBeenCalled();
    });

    it('POST /api/v1/registrations should return conflict for an existing email', async () => {
        registerUserSpy.mockRejectedValue(
            new AuthRegistrationError(
                AuthRegistrationFailure.EmailAlreadyRegistered,
            ),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(409)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Conflict',
            status: 409,
            detail: 'An account with this email is already registered.',
            instance: '/api/v1/registrations',
            code: 'EMAIL_ALREADY_REGISTERED',
        });
    });

    it('POST /api/v1/registrations should return invalid email when the provider rejects the address', async () => {
        registerUserSpy.mockRejectedValue(
            new AuthRegistrationError(AuthRegistrationFailure.InvalidEmail),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Unprocessable Entity',
            status: 422,
            detail: 'The email address is not accepted.',
            instance: '/api/v1/registrations',
            code: 'INVALID_EMAIL',
        });
    });

    it('POST /api/v1/registrations should return invalid request when the provider rejects the registration data', async () => {
        registerUserSpy.mockRejectedValue(
            new AuthRegistrationError(AuthRegistrationFailure.InvalidRequest),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Unprocessable Entity',
            status: 422,
            detail: 'The registration data was rejected.',
            instance: '/api/v1/registrations',
            code: 'INVALID_REQUEST',
        });
    });

    it('POST /api/v1/registrations should return weak password when the provider rejects the password policy', async () => {
        registerUserSpy.mockRejectedValue(
            new AuthRegistrationError(AuthRegistrationFailure.WeakPassword),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Unprocessable Entity',
            status: 422,
            detail: 'The password does not meet the required security policy.',
            instance: '/api/v1/registrations',
            code: 'WEAK_PASSWORD',
        });
    });

    it('POST /api/v1/registrations should return 429 when registration is rate limited', async () => {
        registerUserSpy.mockRejectedValue(
            new AuthRegistrationError(AuthRegistrationFailure.RateLimited),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(429)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Too Many Requests',
            status: 429,
            detail: 'Too many registration attempts. Try again later.',
            instance: '/api/v1/registrations',
            code: 'TOO_MANY_REQUESTS',
        });
    });

    it('POST /api/v1/registrations should return 503 when Supabase Auth is unavailable', async () => {
        registerUserSpy.mockRejectedValue(
            new AuthRegistrationError(
                AuthRegistrationFailure.ProviderUnavailable,
            ),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(503)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Service Unavailable',
            status: 503,
            detail: 'The authentication provider is temporarily unavailable.',
            instance: '/api/v1/registrations',
            code: 'SERVICE_UNAVAILABLE',
        });
    });

    afterAll(async () => {
        registerUserSpy.mockRestore();
        await app.close();
    });
});
