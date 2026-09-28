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
    AuthLoginError,
    AuthLoginFailure,
} from '../src/application/auth/errors/auth-login.error';
import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
} from '../src/application/ports/auth-provider.port';
import { createTestApp } from './helpers/create-test-app';
import { ProblemResponse } from './helpers/problem-response';

describe('User login API (e2e)', () => {
    let app: INestApplication<App>;
    let loginUserSpy: jest.SpiedFunction<AuthProviderPort['loginUser']>;

    beforeAll(async () => {
        app = await createTestApp();
        const provider = app.get<AuthProviderPort>(AUTH_PROVIDER_PORT);
        loginUserSpy = jest.spyOn(provider, 'loginUser');
    });

    beforeEach(() => {
        loginUserSpy.mockReset();
    });

    it('POST /api/v1/sessions should login a user and return session tokens', async () => {
        loginUserSpy.mockResolvedValue({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'access-token',
            refreshToken: 'refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        });

        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(200);

        expect(response.body).toEqual({
            userId: '11111111-1111-4111-8111-111111111111',
            email: 'user@example.com',
            accessToken: 'access-token',
            refreshToken: 'refresh-token',
            expiresIn: 3600,
            tokenType: 'bearer',
        });

        expect(loginUserSpy).toHaveBeenCalledWith({
            email: 'user@example.com',
            password: 'StrongPassword123!',
        });
    });

    it('POST /api/v1/sessions should reject invalid login fields', async () => {
        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
            .send({
                email: 'not-an-email',
                password: '',
                role: 'administrator',
            })
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);

        const body = response.body as ProblemResponse;

        expect(body.code).toBe('VALIDATION_ERROR');

        expect(body.errors).toEqual(
            expect.arrayContaining([
                'email must be an email',
                'property role should not exist',
            ]),
        );

        expect(loginUserSpy).not.toHaveBeenCalled();
    });

    it('POST /api/v1/sessions should return unauthorized for invalid credentials', async () => {
        loginUserSpy.mockRejectedValue(
            new AuthLoginError(AuthLoginFailure.InvalidCredentials),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
            .send({
                email: 'user@example.com',
                password: 'WrongPassword!',
            })
            .expect(401)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Unauthorized',
            status: 401,
            detail: 'The email or password is incorrect.',
            instance: '/api/v1/sessions',
            code: 'INVALID_CREDENTIALS',
        });
    });

    it('POST /api/v1/sessions should reject an unconfirmed email', async () => {
        loginUserSpy.mockRejectedValue(
            new AuthLoginError(AuthLoginFailure.EmailNotConfirmed),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
            .send({
                email: 'user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(403)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Forbidden',
            status: 403,
            detail: 'The email address must be confirmed before signing in.',
            instance: '/api/v1/sessions',
            code: 'EMAIL_NOT_CONFIRMED',
        });
    });

    it('POST /api/v1/sessions should return invalid request when Supabase rejects the login data', async () => {
        loginUserSpy.mockRejectedValue(
            new AuthLoginError(AuthLoginFailure.InvalidRequest),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
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
            detail: 'The login data was rejected.',
            instance: '/api/v1/sessions',
            code: 'INVALID_REQUEST',
        });
    });

    it('POST /api/v1/sessions should return 429 when login is rate limited', async () => {
        loginUserSpy.mockRejectedValue(
            new AuthLoginError(AuthLoginFailure.RateLimited),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
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
            detail: 'Too many login attempts. Try again later.',
            instance: '/api/v1/sessions',
            code: 'TOO_MANY_REQUESTS',
        });
    });

    it('POST /api/v1/sessions should return 503 when Supabase Auth is unavailable', async () => {
        loginUserSpy.mockRejectedValue(
            new AuthLoginError(AuthLoginFailure.ProviderUnavailable),
        );

        const response = await request(app.getHttpServer())
            .post('/api/v1/sessions')
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
            instance: '/api/v1/sessions',
            code: 'SERVICE_UNAVAILABLE',
        });
    });

    afterAll(async () => {
        loginUserSpy.mockRestore();
        await app.close();
    });
});
