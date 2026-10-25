import { INestApplication } from '@nestjs/common';
import { OpenAPIObject } from '@nestjs/swagger';
import { afterAll, beforeAll, beforeEach, describe, expect, it, jest } from '@jest/globals';
import request from 'supertest';
import { App } from 'supertest/types';

import {
  EmailConfirmationError,
  EmailConfirmationFailure,
} from '../src/application/auth/errors/email-confirmation.error';
import {
  AUTH_PROVIDER_PORT,
  type AuthProviderPort,
} from '../src/application/ports/auth-provider.port';
import { createTestApp } from './helpers/create-test-app';
import { ProblemResponse } from './helpers/problem-response';

const confirmationPath = '/api/v1/registrations/email-confirmations';
const resendPath = '/api/v1/registrations/email-confirmation-requests';
const email = 'user@example.com';

describe('Email confirmation and resend API (e2e)', () => {
  let app: INestApplication<App>;
  let confirmSpy: jest.SpiedFunction<AuthProviderPort['confirmEmail']>;
  let resendSpy: jest.SpiedFunction<AuthProviderPort['resendEmailConfirmation']>;

  beforeAll(async () => {
    app = await createTestApp();
    const provider = app.get<AuthProviderPort>(AUTH_PROVIDER_PORT);
    confirmSpy = jest.spyOn(provider, 'confirmEmail');
    resendSpy = jest.spyOn(provider, 'resendEmailConfirmation');
  });

  beforeEach(() => {
    confirmSpy.mockReset();
    resendSpy.mockReset();
  });

  afterAll(async () => {
    jest.restoreAllMocks();
    await app.close();
  });

  it('confirms a six-digit code without a Bearer token and returns the session', async () => {
    const session = {
      userId: '11111111-1111-4111-8111-111111111111',
      email,
      accessToken: 'test-access-token',
      refreshToken: 'test-refresh-token',
      expiresIn: 3600,
      tokenType: 'bearer',
    };
    confirmSpy.mockResolvedValue(session);

    const response = await request(app.getHttpServer())
      .post(confirmationPath)
      .send({ email, code: '012345' })
      .expect(200)
      .expect('Cache-Control', 'no-store');

    expect(response.body).toEqual(session);
    expect(confirmSpy).toHaveBeenCalledWith({ email, code: '012345' });
  });

  it('rejects an invalid code format before calling the provider', async () => {
    const response = await request(app.getHttpServer())
      .post(confirmationPath)
      .send({ email, code: '12345' })
      .expect(422)
      .expect('Content-Type', /application\/problem\+json/);

    expect((response.body as ProblemResponse).code).toBe('VALIDATION_ERROR');
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('returns 401 when the provider rejects an invalid or expired code', async () => {
    confirmSpy.mockRejectedValue(new EmailConfirmationError(EmailConfirmationFailure.InvalidCode));

    const response = await request(app.getHttpServer())
      .post(confirmationPath)
      .send({ email, code: '654321' })
      .expect(401)
      .expect('Content-Type', /application\/problem\+json/);

    expect((response.body as ProblemResponse).code).toBe('INVALID_EMAIL_CONFIRMATION_CODE');
  });

  it('accepts resend requests with the same neutral response for different emails', async () => {
    resendSpy.mockResolvedValue(undefined);

    const first = await request(app.getHttpServer()).post(resendPath).send({ email }).expect(202);
    const secondEmail = 'another@example.com';
    const second = await request(app.getHttpServer())
      .post(resendPath)
      .send({ email: secondEmail })
      .expect(202);

    expect(first.body).toEqual(second.body);
    expect(first.body).toEqual({ message: expect.any(String) });
    expect(resendSpy).toHaveBeenNthCalledWith(1, email);
    expect(resendSpy).toHaveBeenNthCalledWith(2, secondEmail);
  });

  it('rejects an invalid resend email before calling the provider', async () => {
    const response = await request(app.getHttpServer())
      .post(resendPath)
      .send({ email: 'invalid-email' })
      .expect(422)
      .expect('Content-Type', /application\/problem\+json/);

    expect((response.body as ProblemResponse).code).toBe('VALIDATION_ERROR');
    expect(resendSpy).not.toHaveBeenCalled();
  });

  it('includes both endpoints and their success responses in OpenAPI', async () => {
    const response = await request(app.getHttpServer()).get('/openapi.json').expect(200);
    const document = response.body as OpenAPIObject;

    expect(document.paths[confirmationPath]?.post?.responses['200']).toBeDefined();
    expect(document.paths[resendPath]?.post?.responses['202']).toBeDefined();
  });
});
