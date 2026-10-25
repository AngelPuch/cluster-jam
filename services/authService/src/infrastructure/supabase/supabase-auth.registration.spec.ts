import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { Logger } from '@nestjs/common';
import {
  EmailConfirmationError,
  EmailConfirmationFailure,
} from '../../application/auth/errors/email-confirmation.error';
import { AuthRegistrationFailure } from '../../application/auth/errors/auth-registration.error';
import { UserRegistrationStatus } from '../../application/ports/auth-provider.port';
import {
  configService,
  confirmationInput as input,
  confirmationJson as json,
  confirmedSession,
  createAuthError,
  createUser,
  getSignUpSpy,
} from '../../../test/helpers/supabase-auth.fixtures';

import { SupabaseAuthAdapter } from './supabase-auth.adapter';

describe('SupabaseAuthAdapter.registerUser', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should register a user pending email confirmation', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: createUser(1),
        session: null,
      },
      error: null,
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).resolves.toEqual({
      userId: '11111111-1111-4111-8111-111111111111',
      email: 'user@example.com',
      status: UserRegistrationStatus.PendingEmailConfirmation,
    });

    expect(signUpSpy).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'StrongPassword123!',
    });
  });

  it('should reject an obfuscated duplicate user response', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: createUser(0),
        session: null,
      },
      error: null,
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).rejects.toMatchObject({
      failure: AuthRegistrationFailure.EmailAlreadyRegistered,
    });
  });

  it('should translate an existing user error', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: null,
        session: null,
      },
      error: createAuthError('user_already_exists'),
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).rejects.toMatchObject({
      failure: AuthRegistrationFailure.EmailAlreadyRegistered,
    });
  });

  it('should translate a weak password error', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: null,
        session: null,
      },
      error: createAuthError('weak_password'),
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).rejects.toMatchObject({
      failure: AuthRegistrationFailure.WeakPassword,
    });
  });

  it('should translate an invalid email error', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: null,
        session: null,
      },
      error: createAuthError('email_address_invalid'),
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).rejects.toMatchObject({
      failure: AuthRegistrationFailure.InvalidEmail,
    });
  });

  it('should translate a registration rate limit error', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: null,
        session: null,
      },
      error: createAuthError('over_email_send_rate_limit', 429),
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).rejects.toMatchObject({
      failure: AuthRegistrationFailure.RateLimited,
    });
  });

  it('should translate provider failures as unavailable', async () => {
    const adapter = new SupabaseAuthAdapter(configService);

    const signUpSpy = getSignUpSpy(adapter);

    signUpSpy.mockResolvedValue({
      data: {
        user: null,
        session: null,
      },
      error: createAuthError('unexpected_failure', 500),
    });

    await expect(
      adapter.registerUser({
        email: 'user@example.com',
        password: 'StrongPassword123!',
      }),
    ).rejects.toMatchObject({
      failure: AuthRegistrationFailure.ProviderUnavailable,
    });
  });
});

describe('SupabaseAuthAdapter registration confirmation', () => {
  let adapter: SupabaseAuthAdapter;
  let fetchSpy: jest.SpiedFunction<typeof fetch>;
  let warn: jest.SpiedFunction<Logger['warn']>;

  beforeEach(() => {
    adapter = new SupabaseAuthAdapter(configService);
    fetchSpy = jest.spyOn(globalThis, 'fetch');
    warn = jest.spyOn(Logger.prototype, 'warn').mockImplementation(() => {});
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('verifies only signup proof and maps a confirmed session', async () => {
    fetchSpy.mockResolvedValue(json(200, confirmedSession()));
    await expect(adapter.confirmEmail(input)).resolves.toEqual({
      userId: confirmedSession().user.id,
      email: input.email,
      accessToken: confirmedSession().access_token,
      refreshToken: confirmedSession().refresh_token,
      expiresIn: 3600,
      tokenType: 'bearer',
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(
      'https://test-project.supabase.co/auth/v1/verify',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          email: input.email,
          token: '012345',
          type: 'signup',
        }),
        headers: {
          apikey: 'test-publishable-key',
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        signal: expect.any(AbortSignal),
      }),
    );
    expect(warn).not.toHaveBeenCalled();
  });

  it.each([
    [403, { error_code: 'otp_expired' }, EmailConfirmationFailure.InvalidCode],
    [403, { code: 'otp_expired' }, EmailConfirmationFailure.InvalidCode],
    [400, { code: 'validation_failed' }, EmailConfirmationFailure.InvalidCode],
    [401, {}, EmailConfirmationFailure.InvalidCode],
    [422, {}, EmailConfirmationFailure.InvalidCode],
    [403, { code: 'user_banned' }, EmailConfirmationFailure.NotAllowed],
    [429, {}, EmailConfirmationFailure.RateLimited],
    [400, { code: 'over_request_rate_limit' }, EmailConfirmationFailure.RateLimited],
    [403, { code: 'otp_disabled' }, EmailConfirmationFailure.ProviderUnavailable],
    [403, { code: 'email_provider_disabled' }, EmailConfirmationFailure.ProviderUnavailable],
    [503, { code: 'otp_expired' }, EmailConfirmationFailure.ProviderUnavailable],
    [202, {}, EmailConfirmationFailure.ProviderUnavailable],
  ] as const)('maps provider status %s safely', async (status, body, failure) => {
    fetchSpy.mockResolvedValue(json(status, body));
    await expect(adapter.confirmEmail(input)).rejects.toEqual(new EmailConfirmationError(failure));
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it.each([
    null,
    {},
    { ...confirmedSession(), access_token: '' },
    { ...confirmedSession(), refresh_token: '' },
    { ...confirmedSession(), expires_in: 0 },
    { ...confirmedSession(), token_type: 'other' },
    { ...confirmedSession(), user: null },
    {
      ...confirmedSession(),
      user: { ...confirmedSession().user, email_confirmed_at: null },
    },
    { ...confirmedSession(), user: { ...confirmedSession().user, id: '' } },
    confirmedSession('someone@example.com'),
  ])('rejects malformed, unconfirmed or mismatched session data', async (payload) => {
    fetchSpy.mockResolvedValue(json(200, payload));
    await expect(adapter.confirmEmail(input)).rejects.toEqual(
      new EmailConfirmationError(EmailConfirmationFailure.ProviderUnavailable),
    );
  });

  it('accepts a normalized provider email', async () => {
    fetchSpy.mockResolvedValue(json(200, confirmedSession()));
    await expect(
      adapter.confirmEmail({ ...input, email: 'USER@example.com' }),
    ).resolves.toHaveProperty('email', input.email);
  });

  it.each(['network', 'timeout', 'invalid-json'])(
    'sanitizes %s failures without retrying consumed proof',
    async (kind) => {
      if (kind === 'invalid-json') {
        fetchSpy.mockResolvedValue(new Response('private-payload', { status: 200 }));
      } else {
        fetchSpy.mockRejectedValue(
          kind === 'timeout'
            ? new DOMException('private-timeout', 'TimeoutError')
            : new Error('private-network'),
        );
      }
      await expect(adapter.confirmEmail(input)).rejects.toEqual(
        new EmailConfirmationError(EmailConfirmationFailure.ProviderUnavailable),
      );
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(warn).not.toHaveBeenCalled();
    },
  );

  it('keeps concurrent users separate without client session state', async () => {
    fetchSpy.mockImplementation((_url, options) => {
      const body = JSON.parse(typeof options?.body === 'string' ? options.body : '{}') as {
        email: string;
      };
      return Promise.resolve(json(200, confirmedSession(body.email)));
    });
    const [first, second] = await Promise.all([
      adapter.confirmEmail(input),
      adapter.confirmEmail({
        email: 'second@example.com',
        code: '654321',
      }),
    ]);
    expect(first.email).toBe(input.email);
    expect(second.email).toBe('second@example.com');
  });

  it.each([200, 400, 422, 429, 503])(
    'keeps resend status %s neutral and logs no input',
    async (status) => {
      fetchSpy.mockResolvedValue(json(status, { msg: 'private-provider-data' }));
      await expect(adapter.resendEmailConfirmation(input.email)).resolves.toBeUndefined();
      expect(fetchSpy).toHaveBeenCalledWith(
        'https://test-project.supabase.co/auth/v1/resend',
        expect.objectContaining({
          body: JSON.stringify({
            type: 'signup',
            email: input.email,
          }),
        }),
      );
      expect(warn.mock.calls).toEqual(
        status === 200 ? [] : [['Email confirmation dispatch failed.']],
      );
    },
  );

  it('keeps resend transport failures neutral with a fixed warning', async () => {
    fetchSpy.mockRejectedValue(new Error('private-provider-data'));
    await expect(adapter.resendEmailConfirmation(input.email)).resolves.toBeUndefined();
    expect(warn.mock.calls).toEqual([['Email confirmation dispatch failed.']]);
  });
});
