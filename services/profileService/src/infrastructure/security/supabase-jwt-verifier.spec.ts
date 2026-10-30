import { jest } from '@jest/globals';
import { ConfigService } from '@nestjs/config';
import { SignJWT, type JWK } from 'jose';
import { SupabaseJwtVerifier } from './supabase-jwt-verifier';
import { AccessTokenFailure } from '../../application/security/access-token.error';
import { AppRole } from '../../application/security/verified-identity';
import {
    createSigningKeys,
    signAccessToken,
    userClaims,
    TEST_SUPABASE_URL,
    TEST_ISSUER,
    type SigningKeys,
} from '../../../test/helpers/jwt.fixture';

describe('Local Supabase JWT verification', () => {
    let keys: SigningKeys;
    let verifier: SupabaseJwtVerifier;
    let published: JWK[];
    let fetchSpy: jest.SpiedFunction<typeof fetch>;
    const settings = {
        APP_ENV: 'test',
        SUPABASE_URL: TEST_SUPABASE_URL,
        SUPABASE_JWKS_URL: TEST_ISSUER + '/.well-known/jwks.json',
    };

    beforeAll(async () => {
        keys = await createSigningKeys();
    });
    beforeEach(() => {
        published = [keys.es.jwk, keys.rs.jwk];
        fetchSpy = jest
            .spyOn(globalThis, 'fetch')
            .mockImplementation(() => Promise.resolve(Response.json({ keys: published })));
        verifier = new SupabaseJwtVerifier(new ConfigService(settings));
    });
    afterEach(() => jest.restoreAllMocks());

    it.each(['es', 'rs'] as const)('accepts a real %s signature and returns only immutable identity', async (key) => {
        const claims = userClaims();
        const token = await signAccessToken(keys, claims, key);
        const identity = await verifier.verify(token);
        expect(identity).toEqual({ userId: claims.sub, appRole: AppRole.Client });
        expect(Object.isFrozen(identity)).toBe(true);
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('accepts administrators only from protected metadata and ignores user_metadata elevation', async () => {
        const client = await signAccessToken(keys, userClaims({ user_metadata: { app_role: 'administrador' } }));
        const administrator = await signAccessToken(keys, userClaims({ app_metadata: { app_role: 'administrador' } }));
        expect((await verifier.verify(client)).appRole).toBe(AppRole.Client);
        expect((await verifier.verify(administrator)).appRole).toBe(AppRole.Administrator);
    });

    it.each(['sub', 'exp', 'iss', 'aud'])('rejects missing %s', async (claim) => {
        const claims = userClaims();
        delete claims[claim];
        await expect(verifier.verify(await signAccessToken(keys, claims))).rejects.toMatchObject({
            failure: AccessTokenFailure.InvalidAccessToken,
        });
    });

    it.each([
        ['sub', 'invalid'],
        ['sub', 7],
        ['exp', 1],
        ['exp', '9999999999'],
        ['exp', true],
        ['exp', null],
        ['iss', 'https://attacker.example/auth/v1'],
        ['aud', 'service_role'],
        ['role', 'service_role'],
        ['is_anonymous', true],
        ['is_anonymous', null],
        ['is_anonymous', 'false'],
        ['nbf', 9999999999],
    ])('rejects invalid signed claim %s=%j', async (claim, value) => {
        await expect(
            verifier.verify(await signAccessToken(keys, userClaims({ [String(claim)]: value }))),
        ).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
    });

    it.each([
        undefined,
        null,
        {},
        'administrador',
        [],
        { app_role: 'Administrador' },
        { app_role: 'owner' },
        { app_role: ['cliente'] },
    ])('rejects invalid protected roles %j', async (metadata) => {
        await expect(
            verifier.verify(
                await signAccessToken(
                    keys,
                    userClaims({ app_metadata: metadata, user_metadata: { app_role: 'administrador' } }),
                ),
            ),
        ).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAppRole });
    });

    it.each(['', 'malformed', 'a.b.c', 'x'.repeat(16385)])(
        'rejects malformed/bounded input before JWKS retrieval',
        async (token) => {
            await expect(verifier.verify(token)).rejects.toMatchObject({
                failure: AccessTokenFailure.InvalidAccessToken,
            });
            expect(fetchSpy).not.toHaveBeenCalled();
        },
    );

    it('rejects symmetric and unsigned credentials before retrieving keys', async () => {
        const symmetric = await new SignJWT(userClaims())
            .setProtectedHeader({ alg: 'HS256', kid: 'es-initial' })
            .sign(new TextEncoder().encode('test-only-key-material'.repeat(4)));
        const unsigned =
            Buffer.from(JSON.stringify({ alg: 'none', kid: 'es-initial' })).toString('base64url') +
            '.' +
            Buffer.from(JSON.stringify(userClaims())).toString('base64url') +
            '.';
        for (const token of [symmetric, unsigned]) {
            await expect(verifier.verify(token)).rejects.toMatchObject({
                failure: AccessTokenFailure.InvalidAccessToken,
            });
        }
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('rejects missing, blank or oversized key identifiers', async () => {
        for (const kid of [undefined, '', 'x'.repeat(257)]) {
            await expect(
                verifier.verify(await signAccessToken(keys, userClaims(), 'es', { kid })),
            ).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
        }
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('rejects forged signatures and edited payloads', async () => {
        const forged = await signAccessToken(keys, userClaims(), 'rotated', { kid: 'es-initial' });
        await expect(verifier.verify(forged)).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
        const original = await signAccessToken(keys);
        const [header, , signature] = original.split('.');
        const edited =
            header +
            '.' +
            Buffer.from(JSON.stringify(userClaims({ app_metadata: { app_role: 'administrador' } }))).toString(
                'base64url',
            ) +
            '.' +
            signature;
        await expect(verifier.verify(edited)).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
    });

    it('fetches only the configured JWKS and ignores a token-provided key URL', async () => {
        const token = await signAccessToken(keys, userClaims(), 'rotated', {
            kid: 'es-initial',
            jku: 'https://attacker.example/keys',
        });
        await expect(verifier.verify(token)).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
        expect(fetchSpy).toHaveBeenCalledWith(
            settings.SUPABASE_JWKS_URL,
            expect.objectContaining({ method: 'GET', redirect: 'manual' }),
        );
    });

    it('shares one download across concurrent verifications', async () => {
        const token = await signAccessToken(keys);
        expect(await Promise.all(Array.from({ length: 32 }, () => verifier.verify(token)))).toHaveLength(32);
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it('refreshes an unknown rotated key only after the 30-second cooldown', async () => {
        const now = Date.now();
        const clock = jest.spyOn(Date, 'now').mockReturnValue(now);
        await verifier.verify(await signAccessToken(keys));
        published.push(keys.rotated.jwk);
        const token = await signAccessToken(keys, userClaims(), 'rotated');
        await expect(verifier.verify(token)).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
        clock.mockReturnValue(now + 31000);
        await expect(verifier.verify(token)).resolves.toMatchObject({ appRole: AppRole.Client });
        expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('removes retired keys after the ten-minute cache lifetime', async () => {
        const now = Date.now();
        const clock = jest.spyOn(Date, 'now').mockReturnValue(now);
        const token = await signAccessToken(keys);
        await verifier.verify(token);
        published = [keys.rotated.jwk];
        clock.mockReturnValue(now + 601000);
        await expect(verifier.verify(token)).rejects.toMatchObject({ failure: AccessTokenFailure.InvalidAccessToken });
        expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('uses warm keys during an outage until the cache expires, then fails closed', async () => {
        const now = Date.now();
        const clock = jest.spyOn(Date, 'now').mockReturnValue(now);
        const token = await signAccessToken(keys);
        await verifier.verify(token);
        fetchSpy.mockRejectedValue(new Error('private-provider-detail'));
        await expect(verifier.verify(token)).resolves.toMatchObject({ appRole: AppRole.Client });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
        clock.mockReturnValue(now + 601000);
        await expect(verifier.verify(token)).rejects.toMatchObject({
            failure: AccessTokenFailure.KeysUnavailable,
            message: 'SERVICE_UNAVAILABLE',
        });
    });

    it.each(['unavailable', 'malformed-json', 'invalid-set', 'empty', 'ambiguous', 'redirect'])(
        'handles %s JWKS as a safe outage',
        async (mode) => {
            fetchSpy.mockImplementation(() => {
                if (mode === 'unavailable') return Promise.reject(new Error('private-provider-detail'));
                if (mode === 'malformed-json') return Promise.resolve(new Response('{broken', { status: 200 }));
                if (mode === 'redirect')
                    return Promise.resolve(
                        new Response(null, { status: 302, headers: { Location: 'https://attacker.example' } }),
                    );
                return Promise.resolve(
                    Response.json({
                        keys: mode === 'empty' ? [] : mode === 'ambiguous' ? [keys.es.jwk, keys.es.jwk] : 'invalid',
                    }),
                );
            });
            await expect(verifier.verify(await signAccessToken(keys))).rejects.toMatchObject({
                failure: AccessTokenFailure.KeysUnavailable,
                message: 'SERVICE_UNAVAILABLE',
            });
        },
    );
});
