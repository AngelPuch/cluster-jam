import { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { afterAll, beforeAll, describe, expect, it } from '@jest/globals';
import { randomUUID } from 'node:crypto';
import { connect, type Channel, type ChannelModel } from 'amqplib';
import { Pool } from 'pg';
import request from 'supertest';
import type { App } from 'supertest/types';

import { AppModule } from '../src/app.module';
import { PublishRegistrationEventsService } from '../src/application/events/publish-registration-events.service';
import { RegistrationPublicationError } from '../src/application/events/registration-event';
import { PostgresRegistrationOutboxAdapter } from '../src/infrastructure/outbox/postgres-registration-outbox.adapter';
import { RegistrationOutboxWorker } from '../src/interfaces/workers/registration-outbox.worker';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';

interface OutboxState {
    id: string;
    publicado_en: Date | null;
    intentos: number;
    proximo_intento_en: Date | null;
}

describe('Registration outbox with real Supabase/Postgres/RabbitMQ', () => {
    let app: INestApplication<App>;
    let service: PublishRegistrationEventsService;
    let admin: Pool;
    let runtime: Pool;
    let connection: ChannelModel;
    let channel: Channel;
    let queue: string;
    const createdUsers: string[] = [];

    beforeAll(async () => {
        if (
            process.env.OUTBOX_INTEGRATION_LOCAL !== 'true' ||
            process.env.SUPABASE_URL !== 'http://127.0.0.1:54321' ||
            process.env.OUTBOX_DATABASE_SSL !== 'false'
        ) {
            throw new Error(
                'Use the explicitly authorized disposable local integration stack.',
            );
        }
        for (const key of [
            'OUTBOX_TEST_ADMIN_DATABASE_URL',
            'OUTBOX_DATABASE_URL',
            'RABBITMQ_URL',
        ]) {
            const url = new URL(process.env[key] ?? '');
            if (!['127.0.0.1', 'localhost'].includes(url.hostname))
                throw new Error('Integration dependencies must be local.');
        }
        admin = new Pool({
            connectionString: process.env.OUTBOX_TEST_ADMIN_DATABASE_URL,
        });
        runtime = new Pool({
            connectionString: process.env.OUTBOX_DATABASE_URL,
        });
        const initial = await admin.query<{ count: string }>(
            'SELECT count(*) FROM integration.auth_outbox WHERE publicado_en IS NULL',
        );
        if (initial.rows[0].count !== '0')
            throw new Error(
                'Use a disposable database with no pending events.',
            );
        connection = await connect(process.env.RABBITMQ_URL!);
        channel = await connection.createChannel();
        await channel.assertExchange('identity.events', 'topic', {
            durable: true,
        });
        const result = await channel.assertQueue(
            `auth.branch10.test.${randomUUID()}`,
            { durable: true, autoDelete: false },
        );
        queue = result.queue;
        await channel.bindQueue(
            queue,
            'identity.events',
            'identity.user.registered.v1',
        );
        const module = await Test.createTestingModule({ imports: [AppModule] })
            .overrideProvider(RegistrationOutboxWorker)
            .useValue({})
            .compile();
        app = module.createNestApplication();
        configureHttpApplication(app);
        await app.init();
        service = app.get(PublishRegistrationEventsService);
    });

    afterAll(async () => {
        await app?.close();
        if (queue) await channel.deleteQueue(queue);
        await connection?.close();
        for (const userId of createdUsers) {
            await admin.query(
                'DELETE FROM integration.auth_outbox WHERE agregado_id = $1',
                [userId],
            );
            await admin.query('DELETE FROM auth.users WHERE id = $1', [userId]);
        }
        await runtime?.end();
        await admin?.end();
    });

    async function register(): Promise<OutboxState> {
        const email = `branch10-${randomUUID()}@example.com`;
        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({ email, password: 'StrongPassword123!' })
            .expect(201);
        const body = response.body as { userId: string; status: string };
        createdUsers.push(body.userId);
        expect(body.status).toBe('PENDING_EMAIL_CONFIRMATION');
        const result = await admin.query<OutboxState>(
            'SELECT id, publicado_en, intentos, proximo_intento_en FROM integration.auth_outbox WHERE agregado_id = $1',
            [body.userId],
        );
        expect(result.rows).toHaveLength(1);
        expect(result.rows[0].publicado_en).toBeNull();
        return result.rows[0];
    }

    it('publishes the actual trigger row and marks it only after a routed confirm', async () => {
        const row = await register();
        await expect(service.execute(1)).resolves.toEqual({
            published: 1,
            retried: 0,
        });
        const message = await channel.get(queue, { noAck: false });
        expect(message).not.toBe(false);
        if (!message) throw new Error('Expected registration event.');
        const event = JSON.parse(message.content.toString()) as {
            eventId: string;
            data: object;
        };
        expect(event.eventId).toBe(row.id);
        expect(Object.keys(event.data).sort()).toEqual([
            'initialContactEmail',
            'userId',
        ]);
        expect(message.properties.deliveryMode).toBe(2);
        expect(message.properties.messageId).toBe(row.id);
        expect(message.properties.headers?.traceparent).toMatch(
            /^00-[0-9a-f]{32}-[0-9a-f]{16}-00$/,
        );
        channel.ack(message);
        const state = await admin.query<OutboxState>(
            'SELECT * FROM integration.auth_outbox WHERE id = $1',
            [row.id],
        );
        expect(state.rows[0].publicado_en).not.toBeNull();
        await expect(service.execute(1)).resolves.toEqual({
            published: 0,
            retried: 0,
        });
    });

    it('keeps an unrouted message pending and retries with the same id', async () => {
        await channel.unbindQueue(
            queue,
            'identity.events',
            'identity.user.registered.v1',
        );
        const row = await register();
        await expect(service.execute(1)).resolves.toEqual({
            published: 0,
            retried: 1,
        });
        const retry = await admin.query<OutboxState>(
            'SELECT * FROM integration.auth_outbox WHERE id = $1',
            [row.id],
        );
        expect(retry.rows[0].publicado_en).toBeNull();
        expect(retry.rows[0].intentos).toBe(1);
        expect(retry.rows[0].proximo_intento_en).not.toBeNull();
        await channel.bindQueue(
            queue,
            'identity.events',
            'identity.user.registered.v1',
        );
        await admin.query(
            'UPDATE integration.auth_outbox SET proximo_intento_en = now() WHERE id = $1',
            [row.id],
        );
        await expect(service.execute(1)).resolves.toEqual({
            published: 1,
            retried: 0,
        });
        const message = await channel.get(queue, { noAck: false });
        if (!message) throw new Error('Expected retried event.');
        expect(message.properties.messageId).toBe(row.id);
        channel.ack(message);
    });

    it('skips a locked row and persists a progressive retry without publishing it', async () => {
        const row = await register();
        const first = new PostgresRegistrationOutboxAdapter(runtime);
        const second = new PostgresRegistrationOutboxAdapter(runtime);
        let unlock!: () => void;
        let locked!: () => void;
        const gate = new Promise<void>((resolve) => {
            unlock = resolve;
        });
        const acquired = new Promise<void>((resolve) => {
            locked = resolve;
        });
        const active = first.deliverNext(async () => {
            locked();
            await gate;
            throw new RegistrationPublicationError(
                'REGISTRATION_BROKER_UNAVAILABLE',
            );
        });
        await acquired;
        try {
            await expect(
                second.deliverNext(() =>
                    Promise.reject(new Error('Must not run.')),
                ),
            ).resolves.toEqual({ status: 'empty' });
        } finally {
            unlock();
        }
        await expect(active).resolves.toEqual({
            status: 'retry',
            code: 'REGISTRATION_BROKER_UNAVAILABLE',
        });
        const state = await admin.query<OutboxState>(
            'SELECT * FROM integration.auth_outbox WHERE id = $1',
            [row.id],
        );
        expect(state.rows[0].publicado_en).toBeNull();
        expect(state.rows[0].intentos).toBe(1);
    });
});
