export function validateSecurityEnvironment(environment: Record<string, unknown>): Record<string, unknown> {
    const result = { ...environment };
    let project: URL;
    try {
        if (typeof result.SUPABASE_URL !== 'string') throw new Error();
        project = new URL(result.SUPABASE_URL);
        const local =
            ['development', 'test'].includes(String(result.APP_ENV)) &&
            ['localhost', '127.0.0.1', '[::1]'].includes(project.hostname);
        if (
            !(project.protocol === 'https:' || (local && project.protocol === 'http:')) ||
            project.username ||
            project.password ||
            project.href !== project.origin + '/'
        )
            throw new Error();
    } catch {
        throw new Error('Invalid configuration: SUPABASE_URL');
    }
    const issuer = project.origin + '/auth/v1';
    const jwks = issuer + '/.well-known/jwks.json';
    if (result.SUPABASE_ISSUER !== undefined && result.SUPABASE_ISSUER !== issuer) {
        throw new Error('Invalid configuration: SUPABASE_ISSUER must match SUPABASE_URL');
    }
    if (result.SUPABASE_JWKS_URL !== jwks) {
        throw new Error('Invalid configuration: SUPABASE_JWKS_URL must match the trusted project');
    }
    if (result.SUPABASE_AUDIENCE !== undefined && result.SUPABASE_AUDIENCE !== 'authenticated') {
        throw new Error('Invalid configuration: SUPABASE_AUDIENCE');
    }
    result.SUPABASE_URL = project.origin;
    result.SUPABASE_ISSUER = issuer;
    result.SUPABASE_AUDIENCE = 'authenticated';
    return result;
}
