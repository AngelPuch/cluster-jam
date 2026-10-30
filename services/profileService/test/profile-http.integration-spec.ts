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
import { AddressEntity } from '../src/infrastructure/database/entities/address.entity';
import type { AddressResponseDto } from '../src/interfaces/http/addresses/dto/address.dto';

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
    const addressLegacyId = randomUUID();
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
        await historical.query('INSERT INTO app.profile (user_id, name) VALUES ($1, $2)', [
            addressLegacyId,
            'Legacy address owner',
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
        expect(Object.keys(document.paths).sort()).toEqual([
            '/api/v1/profiles/me',
            '/api/v1/profiles/me/addresses',
            '/api/v1/profiles/me/addresses/{addressId}',
            '/health/live',
            '/health/ready',
        ]);
        expect(document.paths[endpoint].patch?.security).toEqual([{ 'supabase-jwt': [] }]);
        expect(document.components.schemas.UpdateProfileDto).toMatchObject({
            additionalProperties: false,
            minProperties: 1,
        });
        expect(document.components.schemas.AddressResponseDto).toMatchObject({
            required: expect.arrayContaining(['id', 'interiorNumber', 'isDefault']) as string[],
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

    describe('Owned address CRUD and aggregate concurrency', () => {
        const path = endpoint + '/addresses';
        const input = {
            label: 'Casa',
            recipient: 'María López',
            street: 'Avenida Reforma',
            exteriorNumber: '123',
            neighborhood: 'Centro',
            municipality: 'Cuauhtémoc',
            state: 'Ciudad de México',
            postalCode: '06000',
            country: 'MX',
        };
        function list(ownerToken = accessToken) {
            return api()
                .get(path)
                .set('Authorization', 'Bearer ' + ownerToken);
        }
        function item(id: string, ownerToken = accessToken) {
            return api()
                .get(path + '/' + id)
                .set('Authorization', 'Bearer ' + ownerToken);
        }
        async function createAddress(fields: object = {}, ownerToken = accessToken) {
            const current = await list(ownerToken).expect(200);
            return api()
                .post(path)
                .set('Authorization', 'Bearer ' + ownerToken)
                .set('If-Match', String(current.headers.etag))
                .send({ ...input, ...fields })
                .expect(201);
        }
        function address(response: request.Response): AddressResponseDto {
            return response.body as AddressResponseDto;
        }
        function change(id: string, fields: object, etag: string, ownerToken = accessToken) {
            return api()
                .patch(path + '/' + id)
                .set('Authorization', 'Bearer ' + ownerToken)
                .set('If-Match', etag)
                .send(fields);
        }
        function remove(id: string, etag: string, ownerToken = accessToken) {
            return api()
                .delete(path + '/' + id)
                .set('Authorization', 'Bearer ' + ownerToken)
                .set('If-Match', etag);
        }

        it('lists an empty book for a PENDING owner without selecting a default or changing the profile', async () => {
            const before = await get().expect(200);
            const response = await list().expect(200, { items: [] }).expect('Cache-Control', 'no-store');
            expect(response.headers.etag).toMatch(/^"[a-f0-9]{64}"$/);
            expect(response.headers.etag).not.toBe((await list(otherToken).expect(200)).headers.etag);
            await list().set('If-None-Match', String(response.headers.etag)).expect(304);
            expect(body(await get().expect(200))).toEqual(body(before));
        });

        it('creates a real owned address with canonical Location, defaults and a usable item ETag', async () => {
            const before = await get().expect(200);
            const created = await createAddress({ label: ' Casa ', country: ' mx ' });
            expect(address(created)).toEqual({
                ...input,
                interiorNumber: null,
                isDefault: false,
                id: expect.stringMatching(/^[a-f0-9-]{36}$/) as string,
            });
            expect(created.headers.location).toBe(path + '/' + address(created).id);
            const stored = await item(address(created).id).expect(200);
            expect(address(stored)).toEqual(address(created));
            expect(stored.headers.etag).toBe(created.headers.etag);
            await item(address(created).id).set('If-None-Match', String(stored.headers.etag)).expect(304);
            expect(await database.getRepository(AddressEntity).countBy({ userId, id: address(created).id })).toBe(1);
            expect(body(await get().expect(200))).toEqual(body(before));
            expect((await get().expect(200)).headers.etag).toBe(before.headers.etag);
        });

        it('edits partially and clears only the optional interior number', async () => {
            const created = await createAddress({ interiorNumber: '4B' });
            const updated = await change(
                address(created).id,
                { label: ' Oficina ', interiorNumber: null },
                String(created.headers.etag),
            ).expect(200);
            expect(address(updated)).toEqual({ ...address(created), label: 'Oficina', interiorNumber: null });
            expect(address(await item(address(created).id).expect(200))).toEqual(address(updated));
        });

        it('treats upper/lowercase UUID paths as the same owned address', async () => {
            const created = await createAddress();
            const id = address(created).id.toUpperCase();
            expect(address(await item(id).expect(200))).toEqual(address(created));
            const updated = await change(id, { label: 'Office' }, String(created.headers.etag)).expect(200);
            await remove(id, String(updated.headers.etag)).expect(204);
            await list().expect(200, { items: [] });
        });

        it('atomically selects/unsets the default and leaves another owner untouched', async () => {
            const foreign = await createAddress({ isDefault: true }, otherToken);
            const first = await createAddress({ label: 'First', isDefault: true });
            const second = await createAddress({ label: 'Second' });
            const beforeSelection = await item(address(second).id).expect(200);
            await change(address(second).id, { isDefault: true }, String(beforeSelection.headers.etag)).expect(200);
            expect(address(await item(address(first).id).expect(200)).isDefault).toBe(false);
            expect(address(await item(address(second).id).expect(200)).isDefault).toBe(true);
            expect(address(await item(address(foreign).id, otherToken).expect(200)).isDefault).toBe(true);
            expect(await database.getRepository(AddressEntity).countBy({ userId, isDefault: true })).toBe(1);
            const selected = await item(address(second).id).expect(200);
            await change(address(second).id, { isDefault: false }, String(selected.headers.etag)).expect(200);
            expect(await database.getRepository(AddressEntity).countBy({ userId, isDefault: true })).toBe(0);
        });

        it('enforces the existing partial unique index even for a direct conflicting SQL write', async () => {
            await createAddress({ isDefault: true });
            const second = await createAddress();
            await expect(
                database.query('UPDATE app.address SET is_default = true WHERE id = $1 AND user_id = $2', [
                    address(second).id,
                    userId,
                ]),
            ).rejects.toMatchObject({ driverError: { code: '23505' } });
            expect(await database.getRepository(AddressEntity).countBy({ userId, isDefault: true })).toBe(1);
        });

        it('deletes only the owned address and does not automatically replace a deleted default', async () => {
            const first = await createAddress({ isDefault: true });
            const second = await createAddress();
            const current = await item(address(first).id).expect(200);
            const deleted = await remove(address(first).id, String(current.headers.etag)).expect(204);
            expect(deleted.text).toBe('');
            await item(address(first).id).expect(404);
            const remaining = await list().expect(200);
            expect(remaining.body as unknown).toEqual({ items: [address(second)] });
            expect(address(await item(address(second).id).expect(200)).isDefault).toBe(false);
        });

        it('hides foreign addresses for reads, updates and deletes, including for an administrator', async () => {
            const foreign = await createAddress({ isDefault: true }, otherToken);
            const foreignId = address(foreign).id;
            const unknown = randomUUID();
            const administrator = await signAccessToken(
                keys,
                userClaims({ sub: userId, iss: project + '/auth/v1', app_metadata: { app_role: 'administrador' } }),
            );
            for (const ownerToken of [accessToken, administrator]) {
                for (const id of [foreignId, unknown]) {
                    for (const response of [
                        await item(id, ownerToken).expect(404),
                        await change(id, { label: 'Forbidden' }, String(foreign.headers.etag), ownerToken).expect(404),
                        await remove(id, String(foreign.headers.etag), ownerToken).expect(404),
                    ])
                        expect(response.body as unknown).toMatchObject({ code: 'ADDRESS_NOT_FOUND' });
                }
            }
            expect(address(await item(foreignId, otherToken).expect(200))).toEqual(address(foreign));
            await list().query({ userId: otherId }).set('x-user-id', otherId).expect(200, { items: [] });
        });

        it.each([
            { userId: 'someone' },
            { id: 'caller-id' },
            { onboardingStatus: 'COMPLETED' },
            { isDefault: 'true' },
            { isDefault: null },
            { country: 'ZZ' },
            { postalCode: 6000 },
            { postalCode: '123456' },
            { recipient: ' ' },
            { street: 'Line\nBreak' },
            { interiorNumber: '' },
            { label: null },
        ])('rejects invalid/privileged create and update fields without changing data %#', async (fields) => {
            const created = await createAddress();
            const before = await list().expect(200);
            const rejectedCreate = await api()
                .post(path)
                .set('Authorization', 'Bearer ' + accessToken)
                .set('If-Match', String(before.headers.etag))
                .send({ ...input, ...fields })
                .expect(422);
            expect(rejectedCreate.body as unknown).toMatchObject({ code: 'VALIDATION_ERROR' });
            await change(address(created).id, fields, String(created.headers.etag)).expect(422);
            expect((await list().expect(200)).body as unknown).toEqual(before.body as unknown);
        });

        it('rejects empty updates, missing fields and unsupported IDs without creating anything', async () => {
            const created = await createAddress();
            await change(address(created).id, {}, String(created.headers.etag)).expect(422);
            await api()
                .post(path)
                .set('Authorization', 'Bearer ' + accessToken)
                .set('If-Match', String((await list()).headers.etag))
                .send({ label: 'Incomplete' })
                .expect(422);
            await item('not-a-uuid').expect(400);
            await change('not-a-uuid', { label: 'Valid' }, String(created.headers.etag)).expect(400);
            await remove('not-a-uuid', String(created.headers.etag)).expect(400);
        });

        it('requires strong If-Match on all writes and rejects a collection tag for an item update', async () => {
            const created = await createAddress();
            const id = address(created).id;
            for (const operation of [
                api().post(path).send(input),
                api()
                    .patch(path + '/' + id)
                    .send({ label: 'Office' }),
                api().delete(path + '/' + id),
            ]) {
                const result = await operation.set('Authorization', 'Bearer ' + accessToken).expect(428);
                expect(result.body as unknown).toMatchObject({ code: 'PRECONDITION_REQUIRED' });
            }
            for (const etag of [
                '*',
                'W/' + String(created.headers.etag),
                '"invalid"',
                String(created.headers.etag) + ', ' + String(created.headers.etag),
            ]) {
                await change(id, { label: 'Office' }, etag).expect(400);
                await remove(id, etag).expect(400);
            }
            await change(id, { label: 'Office' }, String((await list().expect(200)).headers.etag)).expect(412);
        });

        it('fails stale creates, changes and deletes after another address changes', async () => {
            const first = await createAddress();
            const staleBook = await list().expect(200);
            await createAddress({ label: 'Second' });
            await api()
                .post(path)
                .set('Authorization', 'Bearer ' + accessToken)
                .set('If-Match', String(staleBook.headers.etag))
                .send(input)
                .expect(412);
            await change(address(first).id, { label: 'Stale' }, String(first.headers.etag)).expect(412);
            await remove(address(first).id, String(first.headers.etag)).expect(412);
            expect(await database.getRepository(AddressEntity).countBy({ userId })).toBe(2);
        });

        it('allows only one concurrent default creation from the same collection revision', async () => {
            const etag = String((await list().expect(200)).headers.etag);
            const requests = ['First', 'Second'].map((label) =>
                api()
                    .post(path)
                    .set('Authorization', 'Bearer ' + accessToken)
                    .set('If-Match', etag)
                    .send({ ...input, label, isDefault: true }),
            );
            const results = await Promise.all(requests);
            expect(results.map((response) => response.status).sort()).toEqual([201, 412]);
            expect(await database.getRepository(AddressEntity).countBy({ userId })).toBe(1);
            expect(await database.getRepository(AddressEntity).countBy({ userId, isDefault: true })).toBe(1);
        });

        it('allows only one concurrent default selection across distinct addresses from one snapshot', async () => {
            const first = await createAddress();
            const second = await createAddress();
            const firstCurrent = await item(address(first).id).expect(200);
            const secondCurrent = await item(address(second).id).expect(200);
            const results = await Promise.all([
                change(address(first).id, { isDefault: true }, String(firstCurrent.headers.etag)),
                change(address(second).id, { isDefault: true }, String(secondCurrent.headers.etag)),
            ]);
            expect(results.map((response) => response.status).sort()).toEqual([200, 412]);
            expect(await database.getRepository(AddressEntity).countBy({ userId, isDefault: true })).toBe(1);
        });

        it('rolls back default demotion if a later actual database insert fails', async () => {
            const created = await createAddress({ isDefault: true });
            const before = await list().expect(200);
            await database.query(`CREATE FUNCTION app.reject_test_address() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN IF NEW.label = 'Failure probe' THEN RAISE EXCEPTION 'private-driver-detail' USING ERRCODE = '23514'; END IF; RETURN NEW; END $$`);
            await database.query(
                'CREATE TRIGGER reject_test_address BEFORE INSERT ON app.address FOR EACH ROW EXECUTE FUNCTION app.reject_test_address()',
            );
            try {
                const failed = await api()
                    .post(path)
                    .set('Authorization', 'Bearer ' + accessToken)
                    .set('If-Match', String(before.headers.etag))
                    .send({ ...input, label: 'Failure probe', isDefault: true })
                    .expect(503);
                expect(failed.body as unknown).toMatchObject({ code: 'SERVICE_UNAVAILABLE' });
                expect(JSON.stringify(failed.body)).not.toMatch(/private-driver-detail|INSERT|reject_test_address/);
                expect((await list().expect(200)).body as unknown).toEqual(before.body as unknown);
                expect((await item(address(created).id).expect(200)).headers.etag).toBe(created.headers.etag);
            } finally {
                await database.query('DROP TRIGGER reject_test_address ON app.address');
                await database.query('DROP FUNCTION app.reject_test_address()');
            }
        });

        it('does not require completed onboarding or legacy contact repair to manage a real owned address', async () => {
            const legacyToken = await token(addressLegacyId);
            await createAddress({}, legacyToken);
            expect(body(await get(legacyToken).expect(200))).toMatchObject({
                contactEmail: null,
                onboardingStatus: 'PENDING',
            });
        });

        it('never provisions a missing profile during address reads or writes', async () => {
            const missingId = randomUUID();
            const missingToken = await token(missingId);
            const id = randomUUID();
            const etag = '"' + 'a'.repeat(64) + '"';
            for (const response of [
                await list(missingToken).expect(404),
                await item(id, missingToken).expect(404),
                await api()
                    .post(path)
                    .set('Authorization', 'Bearer ' + missingToken)
                    .set('If-Match', etag)
                    .send(input)
                    .expect(404),
                await change(id, { label: 'Office' }, etag, missingToken).expect(404),
                await remove(id, etag, missingToken).expect(404),
            ])
                expect(response.body as unknown).toMatchObject({ code: 'PROFILE_NOT_READY' });
            expect(await database.getRepository(ProfileEntity).findOneBy({ userId: missingId })).toBeNull();
        });

        it('requires authentication on every route and JSON on body mutations', async () => {
            const created = await createAddress();
            const id = address(created).id;
            for (const operation of [
                api().get(path),
                api().get(path + '/' + id),
                api().post(path).send(input),
                api()
                    .patch(path + '/' + id)
                    .send({ label: 'Office' }),
                api().delete(path + '/' + id),
            ])
                await operation.expect(401);
            await api()
                .get(path + '/' + id)
                .set('If-None-Match', String(created.headers.etag))
                .expect(401);
            for (const operation of [api().post(path), api().patch(path + '/' + id)])
                await operation
                    .set('Authorization', 'Bearer ' + accessToken)
                    .set('If-Match', String(created.headers.etag))
                    .set('Content-Type', 'text/plain')
                    .send('private-address-value')
                    .expect(415);
        });
    });
});
