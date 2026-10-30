import { validateSecurityEnvironment } from './security-environment.validation';

describe('Trusted Supabase signing configuration', () => {
    const valid = {
        APP_ENV: 'production',
        SUPABASE_URL: 'https://supabase.example.test',
        SUPABASE_JWKS_URL: 'https://supabase.example.test/auth/v1/.well-known/jwks.json',
    };

    it('derives the issuer and fixed Supabase user audience', () => {
        expect(validateSecurityEnvironment(valid)).toMatchObject({
            SUPABASE_ISSUER: 'https://supabase.example.test/auth/v1',
            SUPABASE_AUDIENCE: 'authenticated',
        });
    });
    it.each([
        undefined,
        'invalid',
        'http://supabase.example.test',
        'https://user:secret@supabase.example.test',
        'https://supabase.example.test/other',
        'https://supabase.example.test/?secret=private',
        'https://supabase.example.test/#private',
    ])('rejects invalid project URLs safely', (SUPABASE_URL) => {
        expect(() => validateSecurityEnvironment({ ...valid, SUPABASE_URL })).toThrow(
            'Invalid configuration: SUPABASE_URL',
        );
    });
    it.each([
        undefined,
        'https://other.example.test/auth/v1/.well-known/jwks.json',
        'https://supabase.example.test/other',
        'https://supabase.example.test/auth/v1/.well-known/jwks.json?secret=private',
    ])('rejects a missing or untrusted JWKS location', (SUPABASE_JWKS_URL) => {
        expect(() => validateSecurityEnvironment({ ...valid, SUPABASE_JWKS_URL })).toThrow('SUPABASE_JWKS_URL');
    });
    it('rejects issuer and audience drift', () => {
        expect(() =>
            validateSecurityEnvironment({ ...valid, SUPABASE_ISSUER: 'https://attacker.example/auth/v1' }),
        ).toThrow('SUPABASE_ISSUER');
        expect(() => validateSecurityEnvironment({ ...valid, SUPABASE_AUDIENCE: 'service_role' })).toThrow(
            'SUPABASE_AUDIENCE',
        );
    });
    it('allows local HTTP only for an explicit local environment', () => {
        const local = {
            SUPABASE_URL: 'http://127.0.0.1:54321',
            SUPABASE_JWKS_URL: 'http://127.0.0.1:54321/auth/v1/.well-known/jwks.json',
        };
        expect(validateSecurityEnvironment({ ...local, APP_ENV: 'test' })).toMatchObject({
            SUPABASE_AUDIENCE: 'authenticated',
        });
        expect(() => validateSecurityEnvironment({ ...local, APP_ENV: 'production' })).toThrow('SUPABASE_URL');
    });
});
