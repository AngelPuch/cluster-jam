// Isolated verification fixture: real HTTPS, ephemeral ES256 signatures, no production identity store.
const { createServer } = require('node:https');
const { readFileSync } = require('node:fs');
const { pathToFileURL } = require('node:url');
async function main() {
    const { generateKeyPair, exportJWK, SignJWT } = await import(
        pathToFileURL(require.resolve('jose', { paths: ['/app'] })).href
    );
    const keys = await generateKeyPair('ES256');
    const jwk = { ...(await exportJWK(keys.publicKey)), kid: 'profile-stack-test', alg: 'ES256', use: 'sig' };
    createServer(
        { cert: readFileSync('/fixture/server.crt'), key: readFileSync('/fixture/server.key'), minVersion: 'TLSv1.2' },
        async (request, response) => {
            try {
                const url = new URL(request.url, 'https://profile-jwks:8443');
                response.setHeader('Content-Type', 'application/json');
                if (url.pathname === '/health/live') return response.end('{"status":"ok"}');
                if (url.pathname === '/auth/v1/.well-known/jwks.json')
                    return response.end(JSON.stringify({ keys: [jwk] }));
                const sub = url.searchParams.get('sub');
                if (url.pathname !== '/_fixture/token' || !/^[a-f0-9-]{36}$/.test(sub || '')) {
                    response.writeHead(404).end();
                    return;
                }
                const token = await new SignJWT({
                    role: 'authenticated',
                    is_anonymous: false,
                    app_metadata: { app_role: 'cliente' },
                })
                    .setProtectedHeader({ alg: 'ES256', kid: jwk.kid })
                    .setSubject(sub)
                    .setIssuer('https://profile-jwks:8443/auth/v1')
                    .setAudience('authenticated')
                    .setIssuedAt()
                    .setExpirationTime('10m')
                    .sign(keys.privateKey);
                response.end(JSON.stringify({ token }));
            } catch {
                response.writeHead(500).end();
            }
        },
    ).listen(8443, '0.0.0.0');
}
main().catch(() => {
    process.stderr.write('Profile TLS identity fixture failed.\n');
    process.exitCode = 1;
});
