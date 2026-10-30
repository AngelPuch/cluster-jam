import { randomUUID } from 'node:crypto';
import { exportJWK, generateKeyPair, CompactSign, type JWTPayload, type JWTHeaderParameters } from 'jose';

export async function createSigningKeys() {
    const [es, rotated, rs] = await Promise.all([
        generateKeyPair('ES256'),
        generateKeyPair('ES256'),
        generateKeyPair('RS256', { modulusLength: 2048 }),
    ]);
    return {
        es: { ...es, jwk: { ...(await exportJWK(es.publicKey)), kid: 'es-initial', alg: 'ES256', use: 'sig' } },
        rotated: {
            ...rotated,
            jwk: { ...(await exportJWK(rotated.publicKey)), kid: 'es-rotated', alg: 'ES256', use: 'sig' },
        },
        rs: { ...rs, jwk: { ...(await exportJWK(rs.publicKey)), kid: 'rs-initial', alg: 'RS256', use: 'sig' } },
    };
}

export type SigningKeys = Awaited<ReturnType<typeof createSigningKeys>>;
export const TEST_SUPABASE_URL = 'https://supabase.example.test';
export const TEST_ISSUER = TEST_SUPABASE_URL + '/auth/v1';

export function userClaims(changes: JWTPayload = {}): JWTPayload {
    const now = Math.floor(Date.now() / 1000);
    return {
        sub: randomUUID(),
        iss: TEST_ISSUER,
        aud: 'authenticated',
        exp: now + 3600,
        iat: now,
        role: 'authenticated',
        app_metadata: { app_role: 'cliente' },
        is_anonymous: false,
        ...changes,
    };
}

export function signAccessToken(
    keys: SigningKeys,
    claims: JWTPayload = userClaims(),
    key: keyof SigningKeys = 'es',
    headers: Partial<JWTHeaderParameters> = {},
): Promise<string> {
    const pair = keys[key];
    // Raw compact JWS permits genuinely signed malformed claims in negative tests.
    return new CompactSign(new TextEncoder().encode(JSON.stringify(claims)))
        .setProtectedHeader({ alg: pair.jwk.alg, kid: pair.jwk.kid, ...headers })
        .sign(pair.privateKey);
}
