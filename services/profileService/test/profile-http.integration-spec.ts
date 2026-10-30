import { jest } from '@jest/globals';
import { Test } from '@nestjs/testing';
import type { INestApplication } from '@nestjs/common';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { DataSource, type MigrationInterface } from 'typeorm';
import request from 'supertest';
import { createDatabaseOptions } from '../src/infrastructure/database/typeorm.options';
import { ProfileEntity } from '../src/infrastructure/database/entities/profile.entity';
import { CreateMinimumProfileService } from '../src/application/profile/create-minimum-profile.service';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';
import { createSigningKeys, signAccessToken, userClaims, type SigningKeys } from './helpers/jwt.fixture';
import type { ProfileResponseDto } from '../src/interfaces/http/profiles/dto/profile-response.dto';

const endpoint = '/api/v1/profiles/me';

describe('Owner HTTP profile with real PostgreSQL, JWT signatures and JWKS', () => {
    let admin: DataSource;
    let database: DataSource;
    let app: INestApplication;
    let jwks: Server;
    let keys: SigningKeys;
    let project: string;
    let provisioning: CreateMinimumProfileService;
    let userId: string;
    let accessToken: string;
    let otherId: string;
    let otherToken: string;
    let databaseName: string;
    const legacyId = randomUUID();
    const jwksPaths: string[] = [];
    const savedEnvironment = { ...process.env };

    beforeAll(async () => {
        const url = new URL(process.env.PROFILE_TEST_DATABASE_URL ?? '');
        if (
            process.env.PROFILE_INTEGRATION_LOCAL !== 'true' ||
            !['127.0.0.1', 'localhost'].includes(url.hostname) ||
            !['postgres:', 'postgresql:'].includes(url.protocol)
        )
            throw new Error('Explicit local integration database required.');
        admin = new DataSource({ type: 'postgres', url: url.toString(), synchronize: false });
        await admin.initialize();
        databaseName = 'profile_test_' + randomUUID().replaceAll('-', '');
        await admin.query(`CREATE DATABASE "${databaseName}"`);
        keys = await createSigningKeys();
        jwks = createServer((incoming, response) => {
            jwksPaths.push(incoming.url ?? '');
            if (incoming.url !== '/auth/v1/.well-known/jwks.json') {
                response.writeHead(404).end();
                return;
            }
            response.writeHead(200, { 'Content-Type': 'application/json' });
            response.end(JSON.stringify({ keys: [keys.es.jwk] }));
        });
        await new Promise<void>((resolve) => jwks.listen(0, '127.0.0.1', resolve));
        project = 'http://127.0.0.1:' + (jwks.address() as AddressInfo).port;
        Object.assign(process.env, {
            APP_ENV: 'test',
            HTTP_PORT: '8080',
            DB_HOST: url.hostname,
            DB_PORT: url.port || '5432',
            DB_USER: decodeURIComponent(url.username),
            DB_PASSWORD: 'local-trust-test-only',
            DB_NAME: databaseName,
            DB_SSL: 'false',
            RABBITMQ_CONSUMER_ENABLED: 'false',
            SUPABASE_URL: project,
            SUPABASE_JWKS_URL: project + '/auth/v1/.well-known/jwks.json',
            LOG_LEVEL: 'ERROR',
        });
        const options = createDatabaseOptions();
        const historical = new DataSource({
            ...options,
            migrations: (options.migrations as Array<new () => MigrationInterface>).slice(0, 2),
        });
        await historical.initialize();
        await historical.runMigrations();
        await historical.query('INSERT INTO app.profile (user_id, name, phone) VALUES ($1, $2, $3)', [
            legacyId,
            'Legacy Customer',
            '5551234567',
        ]);
        await historical.destroy();
        database = new DataSource(options);
        await database.initialize();
        await database.runMigrations();
        const { AppModule } = await import('../src/app.module.js');
        const fixture = await Test.createTestingModule({ imports: [AppModule] })
            .overrideProvider(DataSource)
            .useValue(database)
            .compile();
        app = fixture.createNestApplication();
        app.useLogger(false);
        configureHttpApplication(app);
        await app.listen(0, '127.0.0.1');
        provisioning = app.get(CreateMinimumProfileService);
    });

    beforeEach(async () => {
        userId = randomUUID();
        otherId = randomUUID();
        accessToken = await token(userId);
        otherToken = await token(otherId);
        await provisioning.execute({ eventId: randomUUID(), userId, initialContactEmail: 'initial@example.com' });
        await provisioning.execute({
            eventId: randomUUID(),
            userId: otherId,
            initialContactEmail: 'other@example.com',
        });
    });
    afterAll(async () => {
        jest.restoreAllMocks();
        await app?.close();
        if (database?.isInitialized) await database.destroy();
        if (admin?.isInitialized) {
            if (!/^profile_test_[a-f0-9]{32}$/.test(databaseName)) throw new Error('Unsafe cleanup database name');
            await admin.query(`DROP DATABASE "${databaseName}" WITH (FORCE)`);
            await admin.destroy();
        }
        jwks?.closeAllConnections();
        if (jwks)
            await new Promise<void>((resolve, reject) => jwks.close((error) => (error ? reject(error) : resolve())));
        for (const key of Object.keys(process.env)) if (!(key in savedEnvironment)) delete process.env[key];
        Object.assign(process.env, savedEnvironment);
    });

    function api() {
        return request(app.getHttpServer() as Parameters<typeof request>[0]);
    }
    function token(sub: string) {
        return signAccessToken(keys, userClaims({ sub, iss: project + '/auth/v1' }));
    }
    function get(tokenValue = accessToken) {
        return api()
            .get(endpoint)
            .set('Authorization', 'Bearer ' + tokenValue);
    }
    function patch(body: object | string, etag: string, tokenValue = accessToken) {
        return api()
            .patch(endpoint)
            .set('Authorization', 'Bearer ' + tokenValue)
            .set('If-Match', etag)
            .send(body);
    }
    async function revision() {
        const response = await get().expect(200);
        return String(response.headers.etag);
    }
    function body(response: request.Response): ProfileResponseDto {
        return response.body as ProfileResponseDto;
    }

    it('reads the minimal owner profile with ETag, safe dates and no persistence-only fields', async () => {
        const response = await get().expect(200).expect('Cache-Control', 'no-store');
        expect(body(response)).toEqual({
            userId,
            fullName: null,
            phone: null,
            contactEmail: 'initial@example.com',
            onboardingStatus: 'PENDING',
            createdAt: expect.any(String) as string,
            updatedAt: expect.any(String) as string,
        });
        expect(response.headers.etag).toMatch(/^"[a-f0-9]{64}"$/);
        expect(Number.isNaN(Date.parse(body(response).createdAt))).toBe(false);
    });

    it('uses JWT sub despite query/header identities and rejects arbitrary user lookup', async () => {
        const response = await get().query({ userId: otherId }).set('x-user-id', otherId).expect(200);
        expect(body(response).userId).toBe(userId);
        await api()
            .get('/api/v1/profiles/' + otherId)
            .set('Authorization', 'Bearer ' + accessToken)
            .expect(404);
        expect(body(await get(otherToken).expect(200)).contactEmail).toBe('other@example.com');
    });

    it('authenticates conditional reads before returning 304 for a matching ETag', async () => {
        const etag = await revision();
        const response = await get().set('If-None-Match', etag).expect(304).expect('Cache-Control', 'no-store');
        expect(response.text).toBe('');
        await api().get(endpoint).set('If-None-Match', etag).expect(401);
    });

    it('does not create missing profiles through either GET or PATCH', async () => {
        const missingId = randomUUID();
        const missing = await token(missingId);
        for (const response of [
            await get(missing).expect(404),
            await patch({ fullName: 'María' }, '"' + 'a'.repeat(64) + '"', missing).expect(404),
        ])
            expect(response.body as unknown).toMatchObject({ code: 'PROFILE_NOT_READY' });
        expect(await database.getRepository(ProfileEntity).findOneBy({ userId: missingId })).toBeNull();
    });

    it('persists partial updates, completes without addresses and keeps contact email independent', async () => {
        const first = await patch({ fullName: '  María López  ' }, await revision()).expect(200);
        expect(body(first)).toMatchObject({ fullName: 'María López', phone: null, onboardingStatus: 'PENDING' });
        const second = await patch(
            { phone: '+52 (55) 1234-5678', contactEmail: 'contact@example.com' },
            String(first.headers.etag),
        ).expect(200);
        expect(body(second)).toMatchObject({
            fullName: 'María López',
            phone: '+52 (55) 1234-5678',
            contactEmail: 'contact@example.com',
            onboardingStatus: 'COMPLETED',
        });
        expect(body(await get().expect(200))).toEqual(body(second));
        expect(body(await get(otherToken).expect(200)).fullName).toBeNull();
        await provisioning.execute({ eventId: randomUUID(), userId, initialContactEmail: 'old-login@example.com' });
        expect(body(await get().expect(200))).toEqual(body(second));
        expect(
            await database.query<Array<{ count: string }>>('SELECT count(*) FROM app.address WHERE user_id = $1', [
                userId,
            ]),
        ).toEqual([{ count: '0' }]);
    });

    it.each([
        {},
        { fullName: null },
        { fullName: '   ' },
        { phone: 'abc' },
        { phone: '1'.repeat(16) },
        { contactEmail: 'invalid' },
        { contactEmail: null },
        { fullName: 'x'.repeat(121) },
        { fullName: 'Name\nControl' },
        { userId: 'other' },
        { onboardingStatus: 'COMPLETED' },
        { fullName: 'Valid', roles: ['administrador'] },
        { password: 'private-password' },
    ])('rejects invalid or privileged PATCH input without modifying stored data %#', async (input) => {
        const before = await get().expect(200);
        const response = await patch(input, String(before.headers.etag))
            .expect(422)
            .expect('Content-Type', /application\/problem\+json/);
        expect(response.body as unknown).toMatchObject({ code: 'VALIDATION_ERROR' });
        expect(body(await get().expect(200))).toEqual(body(before));
        expect(JSON.stringify(response.body)).not.toContain('private-password');
    });

    it('requires If-Match and rejects unsupported tag forms', async () => {
        const missing = await api()
            .patch(endpoint)
            .set('Authorization', 'Bearer ' + accessToken)
            .send({ fullName: 'María' })
            .expect(428);
        expect(missing.body as unknown).toMatchObject({ code: 'PRECONDITION_REQUIRED' });
        for (const tag of ['*', 'W/' + (await revision()), '"short"', (await revision()) + ', ' + (await revision())])
            await patch({ fullName: 'María' }, tag).expect(400);
    });

    it('rejects a stale update and prevents lost writes from two concurrent requests', async () => {
        const etag = await revision();
        const results = await Promise.all([patch({ fullName: 'First' }, etag), patch({ phone: '5551234567' }, etag)]);
        expect(results.map((result) => result.status).sort()).toEqual([200, 412]);
        expect(results.find((result) => result.status === 412)?.body as unknown).toMatchObject({
            code: 'PRECONDITION_FAILED',
        });
        const success = results.find((result) => result.status === 200)!;
        expect(body(await get().expect(200))).toEqual(body(success));
        await patch({ contactEmail: 'new@example.com' }, etag).expect(412);
    });

    it('reads historical null email and requires an explicit repair before updating it', async () => {
        const legacyToken = await token(legacyId);
        const before = await get(legacyToken).expect(200);
        expect(body(before)).toMatchObject({ contactEmail: null, onboardingStatus: 'PENDING' });
        const rejected = await patch({ fullName: 'Updated Customer' }, String(before.headers.etag), legacyToken).expect(
            422,
        );
        expect(rejected.body as unknown).toMatchObject({ code: 'PROFILE_CONTACT_EMAIL_REQUIRED' });
        expect(body(await get(legacyToken).expect(200))).toEqual(body(before));
        const repaired = await patch(
            { contactEmail: 'legacy-contact@example.com' },
            String(before.headers.etag),
            legacyToken,
        ).expect(200);
        expect(body(repaired)).toMatchObject({
            fullName: 'Legacy Customer',
            phone: '5551234567',
            contactEmail: 'legacy-contact@example.com',
            onboardingStatus: 'COMPLETED',
        });
    });

    it('rejects invalid credentials before reading or changing a profile', async () => {
        await api().get(endpoint).expect(401).expect('WWW-Authenticate', 'Bearer');
        await api().patch(endpoint).set('Authorization', 'Bearer invalid').send({ fullName: 'María' }).expect(401);
        expect(body(await get().expect(200)).fullName).toBeNull();
        expect(new Set(jwksPaths)).toEqual(new Set(['/auth/v1/.well-known/jwks.json']));
    });

    it('returns safe syntax/media errors and W3C trace correlation without query values', async () => {
        const traceId = '11111111111111111111111111111111';
        const response = await api()
            .patch(endpoint + '?secret=private-value')
            .set('Authorization', 'Bearer ' + accessToken)
            .set('traceparent', `00-${traceId}-2222222222222222-01`)
            .set('Content-Type', 'application/json')
            .send('{"private-value":')
            .expect(400)
            .expect('X-Trace-Id', traceId);
        expect(response.body as unknown).toMatchObject({ traceId, instance: endpoint, code: 'BAD_REQUEST' });
        expect(JSON.stringify(response.body)).not.toContain('private-value');
        await api()
            .patch(endpoint)
            .set('Authorization', 'Bearer ' + accessToken)
            .set('If-Match', await revision())
            .set('Content-Type', 'text/plain')
            .send('private-value')
            .expect(415);
    });

    it('serves Swagger and the implemented versioned contract without authentication', async () => {
        await api()
            .get('/docs/')
            .expect(200)
            .expect('Content-Type', /text\/html/);
        const response = await api().get('/openapi.json').expect(200);
        const document = response.body as {
            paths: Record<string, { get?: unknown; patch?: { security: unknown } }>;
            components: { schemas: Record<string, unknown> };
        };
        expect(Object.keys(document.paths).sort()).toEqual(['/api/v1/profiles/me', '/health/live', '/health/ready']);
        expect(document.paths[endpoint].patch?.security).toEqual([{ 'supabase-jwt': [] }]);
        expect(document.components.schemas.UpdateProfileDto).toMatchObject({
            additionalProperties: false,
            minProperties: 1,
        });
        const committed: unknown = JSON.parse(
            await readFile(resolve(process.cwd(), '../../contracts/openapi/profile/v1/openapi.json'), 'utf8'),
        );
        expect(response.body as unknown).toEqual(committed);
        await api().get('/profiles/me').expect(404);
        await api().get('/health/live').expect(200);
        await api().get('/health/ready').expect(200);
    });

    it('sanitizes an actual database failure without exposing SQL or driver details', async () => {
        // Real PostgreSQL statement failure scoped to this owned test database, then restored.
        await database.query('ALTER TABLE app.profile RENAME TO profile_unavailable');
        try {
            const response = await get()
                .expect(503)
                .expect('Content-Type', /application\/problem\+json/);
            expect(response.body as unknown).toMatchObject({ code: 'SERVICE_UNAVAILABLE' });
            expect(JSON.stringify(response.body)).not.toMatch(/SELECT|relation|profile_unavailable|postgres/i);
        } finally {
            await database.query('ALTER TABLE app.profile_unavailable RENAME TO profile');
        }
    });
});
