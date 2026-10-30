import { Controller, Get, Post, UseGuards, type INestApplication } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { Test } from '@nestjs/testing';
import { createServer, request as httpRequest, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import request from 'supertest';
import { SecurityModule } from '../src/infrastructure/security/security.module';
import { CurrentIdentity } from '../src/interfaces/http/profiles/current-identity.decorator';
import { JwtAuthGuard } from '../src/interfaces/http/profiles/jwt-auth.guard';
import type { VerifiedIdentity } from '../src/application/security/verified-identity';
import { createSigningKeys, signAccessToken, userClaims, type SigningKeys } from './helpers/jwt.fixture';

// These probes are test-only. The service exposes no new public route in this PR.
@Controller('_test')
class IdentityProbeController {
    @Get('identity')
    @UseGuards(JwtAuthGuard)
    getIdentity(@CurrentIdentity() identity: VerifiedIdentity): VerifiedIdentity {
        return identity;
    }

    @Post('identity')
    @UseGuards(JwtAuthGuard)
    postIdentity(@CurrentIdentity() identity: VerifiedIdentity): VerifiedIdentity {
        return identity;
    }

    @Get('missing-guard')
    missingGuard(@CurrentIdentity() identity: VerifiedIdentity): VerifiedIdentity {
        return identity;
    }

    @Get('public')
    publicProbe(): { status: string } {
        return { status: 'ok' };
    }
}

describe('JWT HTTP boundary with real signatures and a real JWKS server', () => {
    let server: Server;
    let keys: SigningKeys;
    let app: INestApplication;
    let project: string;
    let mode: 'ready' | 'unavailable' | 'malformed' | 'redirect' | 'hang' = 'ready';
    let calls = 0;
    let settings: Record<string, string>;
    const paths: string[] = [];

    beforeAll(async () => {
        keys = await createSigningKeys();
        server = createServer((incoming, response) => {
            paths.push(incoming.url ?? '');
            if (incoming.url !== '/auth/v1/.well-known/jwks.json') {
                response.writeHead(404).end();
                return;
            }
            calls++;
            if (mode === 'hang') return;
            if (mode === 'unavailable') {
                response.writeHead(503).end('private-provider-detail');
                return;
            }
            if (mode === 'malformed') {
                response.writeHead(200).end('{private-provider-detail');
                return;
            }
            if (mode === 'redirect') {
                response.writeHead(302, { Location: project + '/untrusted-redirect' }).end();
                return;
            }
            response.writeHead(200, { 'Content-Type': 'application/json' });
            response.end(JSON.stringify({ keys: [keys.es.jwk, keys.rs.jwk] }));
        });
        await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
        project = 'http://127.0.0.1:' + (server.address() as AddressInfo).port;
        settings = {
            APP_ENV: 'test',
            SUPABASE_URL: project,
            SUPABASE_JWKS_URL: project + '/auth/v1/.well-known/jwks.json',
        };
    });

    beforeEach(async () => {
        calls = 0;
        paths.length = 0;
        mode = 'ready';
        const fixture = await Test.createTestingModule({
            imports: [
                ConfigModule.forRoot({ isGlobal: true, ignoreEnvFile: true, load: [() => settings] }),
                SecurityModule,
            ],
            controllers: [IdentityProbeController],
        }).compile();
        app = fixture.createNestApplication();
        app.useLogger(false);
        await app.listen(0, '127.0.0.1');
    });
    afterEach(async () => {
        await app?.close();
    });
    afterAll(async () => {
        server?.closeAllConnections();
        if (server)
            await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
    });

    function api() {
        return request(app.getHttpServer() as Parameters<typeof request>[0]);
    }
    function token(changes: Parameters<typeof userClaims>[0] = {}, key: 'es' | 'rs' | 'rotated' = 'es') {
        return signAccessToken(keys, userClaims({ iss: project + '/auth/v1', ...changes }), key);
    }

    it.each(['es', 'rs'] as const)('authenticates a real %s token without user/session lookup', async (key) => {
        const sub = '11111111-1111-4111-8111-111111111111';
        await api()
            .get('/_test/identity')
            .set('Authorization', 'Bearer ' + (await token({ sub }, key)))
            .expect(200, { userId: sub, appRole: 'cliente' });
        expect(paths).toEqual(['/auth/v1/.well-known/jwks.json']);
    });

    it('uses only JWT sub and protected role despite body, query, headers and user metadata', async () => {
        const sub = '11111111-1111-4111-8111-111111111111';
        const other = '22222222-2222-4222-8222-222222222222';
        const accessToken = await token({ sub, user_metadata: { app_role: 'administrador' } });
        await api()
            .post('/_test/identity')
            .set('Authorization', 'Bearer ' + accessToken)
            .set('x-user-id', other)
            .query({ userId: other })
            .send({ userId: other, identity: { userId: other, appRole: 'administrador' } })
            .expect(201, { userId: sub, appRole: 'cliente' });
    });

    it.each([undefined, 'Basic invalid', 'Bearer invalid', 'Bearer a.b.c', 'Bearer one two'])(
        'returns safe 401 for absent/malformed credentials',
        async (authorization) => {
            const operation = api().get('/_test/identity?token=private-query-value');
            if (authorization) operation.set('Authorization', authorization);
            const response = await operation
                .expect(401)
                .expect('Content-Type', /application\/problem\+json/)
                .expect('Cache-Control', 'no-store')
                .expect('WWW-Authenticate', 'Bearer');
            expect(response.body as unknown).toMatchObject({
                code: 'INVALID_ACCESS_TOKEN',
                instance: '/_test/identity',
                traceId: expect.stringMatching(/^[0-9a-f]{32}$/) as string,
            });
            expect(response.text).not.toContain('private-query-value');
            expect(calls).toBe(0);
        },
    );

    it('rejects duplicate Authorization fields before using JWKS', async () => {
        const valid = await token();
        const address = (app.getHttpServer() as Server).address() as AddressInfo;
        const status = await new Promise<number | undefined>((resolve, reject) => {
            const operation = httpRequest(
                {
                    hostname: '127.0.0.1',
                    port: address.port,
                    path: '/_test/identity',
                    headers: [
                        'Host',
                        '127.0.0.1:' + address.port,
                        'Authorization',
                        'Bearer ' + valid,
                        'Authorization',
                        'Bearer ' + valid,
                    ],
                },
                (response) => {
                    response.resume();
                    response.once('end', () => resolve(response.statusCode));
                },
            );
            operation.once('error', reject);
            operation.end();
        });
        expect(status).toBe(401);
        expect(calls).toBe(0);
    });

    it('does not accept a token supplied only as a cookie or query argument', async () => {
        const valid = await token();
        await api()
            .get('/_test/identity')
            .set('Cookie', 'access_token=' + valid)
            .query({ accessToken: valid })
            .expect(401);
        expect(calls).toBe(0);
    });

    it('rejects expired, forged and wrong-project signatures with 401', async () => {
        const expired = await token({ exp: Math.floor(Date.now() / 1000) - 1 });
        const wrongProject = await token({ iss: 'https://another.example/auth/v1' });
        const forged = await signAccessToken(keys, userClaims({ iss: project + '/auth/v1' }), 'rotated', {
            kid: 'es-initial',
        });
        for (const invalid of [expired, wrongProject, forged]) {
            const response = await api()
                .get('/_test/identity')
                .set('Authorization', 'Bearer ' + invalid)
                .expect(401);
            expect(response.body as unknown).toMatchObject({ code: 'INVALID_ACCESS_TOKEN' });
            expect(response.text).not.toContain(invalid);
        }
    });

    it('returns 403 for a signed credential without a permitted protected role', async () => {
        const response = await api()
            .get('/_test/identity')
            .set(
                'Authorization',
                'Bearer ' +
                    (await token({
                        app_metadata: {},
                        user_metadata: { app_role: 'administrador' },
                    })),
            )
            .expect(403)
            .expect('Content-Type', /application\/problem\+json/);
        expect(response.body as unknown).toMatchObject({ code: 'INVALID_APP_ROLE' });
    });

    it('shares cached keys across requests when the JWKS server becomes unavailable', async () => {
        const valid = await token();
        await api()
            .get('/_test/identity')
            .set('Authorization', 'Bearer ' + valid)
            .expect(200);
        mode = 'unavailable';
        await api()
            .get('/_test/identity')
            .set('Authorization', 'Bearer ' + valid)
            .expect(200);
        expect(calls).toBe(1);
    });

    it.each(['unavailable', 'malformed', 'redirect'] as const)(
        'fails closed with safe 503 for cold JWKS %s',
        async (failure) => {
            mode = failure;
            const valid = await token();
            const response = await api()
                .get('/_test/identity')
                .set('Authorization', 'Bearer ' + valid)
                .expect(503)
                .expect('Content-Type', /application\/problem\+json/)
                .expect('Cache-Control', 'no-store');
            expect(response.body as unknown).toMatchObject({ code: 'SERVICE_UNAVAILABLE' });
            expect(response.text).not.toContain('private-provider-detail');
            expect(response.text).not.toContain(valid);
            expect(paths).toEqual(['/auth/v1/.well-known/jwks.json']);
        },
    );

    it('bounds an unresponsive real JWKS request to five seconds', async () => {
        mode = 'hang';
        const start = Date.now();
        const response = await api()
            .get('/_test/identity')
            .set('Authorization', 'Bearer ' + (await token()))
            .expect(503);
        expect(response.body as unknown).toMatchObject({ code: 'SERVICE_UNAVAILABLE' });
        expect(Date.now() - start).toBeLessThan(7500);
    }, 10000);

    it('keeps public routes public and the identity decorator fail-closed without a guard', async () => {
        await api().get('/_test/public').expect(200, { status: 'ok' });
        await api().get('/_test/missing-guard').expect(401);
        expect(calls).toBe(0);
    });
});
