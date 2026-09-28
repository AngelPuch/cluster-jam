import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import { OpenAPIObject } from '@nestjs/swagger';
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
} from './../src/application/auth/errors/auth-registration.error';
import {
    AuthLoginError,
    AuthLoginFailure,
} from './../src/application/auth/errors/auth-login.error';
import {
    AUTH_PROVIDER_PORT,
    type AuthProviderPort,
    UserRegistrationStatus,
} from './../src/application/ports/auth-provider.port';
import { AppModule } from './../src/app.module';
import { configureHttpApplication } from './../src/interfaces/http/http.setup';

interface ProblemResponse {
    type: string;
    title: string;
    status: number;
    detail: string;
    instance: string;
    code: string;
    errors?: string[];
    traceId?: string;
}

describe('Auth Service API (e2e)', () => {
    let app: INestApplication<App>;
    let fetchSpy: jest.SpiedFunction<typeof fetch>;
    let registerUserSpy: jest.SpiedFunction<AuthProviderPort['registerUser']>;
    let loginUserSpy: jest.SpiedFunction<AuthProviderPort['loginUser']>;

    beforeAll(async () => {
        fetchSpy = jest.spyOn(globalThis, 'fetch');

        const moduleFixture: TestingModule = await Test.createTestingModule({
            imports: [AppModule],
        }).compile();

        app = moduleFixture.createNestApplication();

        configureHttpApplication(app);

        await app.init();

        const authProvider = app.get<AuthProviderPort>(AUTH_PROVIDER_PORT);

        registerUserSpy = jest.spyOn(authProvider, 'registerUser');
        loginUserSpy = jest.spyOn(authProvider, 'loginUser');
    });

    beforeEach(() => {
        fetchSpy.mockReset();
        registerUserSpy.mockReset();
        loginUserSpy.mockReset();
    });

    it('GET /health/live should return 200', async () => {
        await request(app.getHttpServer())
            .get('/health/live')
            .expect(200)
            .expect({
                status: 'ok',
            });
    });

    it('GET /health/ready should return 200 when Supabase Auth is available', async () => {
        fetchSpy.mockResolvedValueOnce(
            new Response(null, {
                status: 200,
            }),
        );

        await request(app.getHttpServer())
            .get('/health/ready')
            .expect(200)
            .expect({
                status: 'ok',
            });
    });

    it('GET /health/ready should return 503 when Supabase Auth is unavailable', async () => {
        fetchSpy.mockResolvedValueOnce(
            new Response(null, {
                status: 503,
            }),
        );

        const response = await request(app.getHttpServer())
            .get('/health/ready')
            .expect(503)
            .expect('Content-Type', /application\/problem\+json/);

        expect(response.body).toEqual({
            type: 'about:blank',
            title: 'Service Unavailable',
            status: 503,
            detail: 'The service is temporarily unavailable.',
            instance: '/health/ready',
            code: 'SERVICE_UNAVAILABLE',
        });
    });

    it('GET /docs should serve Swagger UI', async () => {
        await request(app.getHttpServer())
            .get('/docs')
            .expect(200)
            .expect('Content-Type', /text\/html/);
    });

    it('GET /openapi.json should expose the API contract', async () => {
        const response = await request(app.getHttpServer())
            .get('/openapi.json')
            .expect(200);

        const document = response.body as OpenAPIObject;

        expect(document.info.title).toBe('Cluster JAM Auth Service');

        expect(document.paths['/health/live']?.get).toBeDefined();

        expect(document.paths['/health/ready']?.get).toBeDefined();

        expect(document.paths['/api/v1/health/live']).toBeUndefined();

        expect(document.paths['/api/v1/registrations']?.post).toBeDefined();

        expect(document.paths['/api/v1/sessions']?.post).toBeDefined();

        expect(document.components?.schemas?.ProblemDetailsDto).toBeDefined();

        expect(
            document.components?.securitySchemes?.['supabase-jwt'],
        ).toBeDefined();

        expect(
            JSON.stringify(document.paths['/health/live']?.get?.responses),
        ).toContain('application/problem+json');
    });

    it('should return RFC 9457 problem details for unknown API routes', async () => {
        const traceId = '4bf92f3577b34da6a3ce929d0e0e4736';

        const response = await request(app.getHttpServer())
            .get('/api/v1/missing')
            .set('traceparent', `00-${traceId}-00f067aa0ba902b7-01`)
            .expect(404)
            .expect('Content-Type', /application\/problem\+json/);

        const body = response.body as ProblemResponse;

        expect(body).toEqual({
            type: 'about:blank',
            title: 'Not Found',
            status: 404,
            detail: 'Cannot GET /api/v1/missing',
            instance: '/api/v1/missing',
            code: 'NOT_FOUND',
            traceId,
        });
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
        fetchSpy.mockRestore();
        registerUserSpy.mockRestore();
        loginUserSpy.mockRestore();

        await app.close();
    });
});
