import { randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import { connect, type ChannelModel, type ConfirmChannel, type GetMessage } from 'amqplib';
import { DataSource } from 'typeorm';
import { Test } from '@nestjs/testing';
import request from 'supertest';
import { CreateMinimumProfileService } from '../src/application/profile/create-minimum-profile.service';
import type {
    MinimumProfileInput,
    ProfileProvisioningResult,
} from '../src/application/ports/profile-provisioning.port';
import { validateEnvironment } from '../src/infrastructure/config/environment.validation';
import { ProfileEntity, OnboardingStatus } from '../src/infrastructure/database/entities/profile.entity';
import { InboxMessageEntity } from '../src/infrastructure/database/entities/inbox-message.entity';
import { TypeormProfileProvisioningAdapter } from '../src/infrastructure/database/repositories/typeorm-profile-provisioning.adapter';
import { createDatabaseOptions } from '../src/infrastructure/database/typeorm.options';
import { RabbitMqListener } from '../src/infrastructure/messaging/rabbitmq-listener';
import {
    declareProfileTopology,
    PROFILE_TOPOLOGY as topology,
} from '../src/infrastructure/messaging/rabbitmq-topology';
import { confirmedHandoff } from '../src/infrastructure/messaging/confirmed-handoff';
import { JsonLogger } from '../src/infrastructure/observability/json-logger.service';
import { TraceContextService } from '../src/infrastructure/observability/trace-context.service';
import { UserRegisteredConsumer } from '../src/interfaces/messaging/user-registered.consumer';
import { registrationEvent, registrationMessage } from './helpers/registration.fixture';
// Contract tests execute the real producer; runtime Profile never imports Auth.
import { ConfigService as AuthConfigService } from '../../authService/node_modules/@nestjs/config';
import { createRegistrationEvent } from '../../authService/src/application/events/registration-event';
import { RabbitMqRegistrationEventPublisher } from '../../authService/src/infrastructure/messaging/rabbitmq-registration-event.publisher';

describe('Real RabbitMQ registration delivery and PostgreSQL inbox', () => {
    let adminDatabase: DataSource;
    let database: DataSource;
    const databaseName = `profile_test_${randomUUID().replaceAll('-', '')}`;
    let brokerAdminUri: URL;
    let managementUrl: URL;
    let vhost: string;
    let consumerUser: string;
    let publisherUser: string;
    let adminConnection: ChannelModel;
    let channel: ConfirmChannel;
    let listener: RabbitMqListener | undefined;
    const consumerConnections: ChannelModel[] = [];
    let afterCommit: ((input: MinimumProfileInput, result: ProfileProvisioningResult) => Promise<void>) | undefined;
    let config: Record<string, unknown>;
    let provisions = 0;
    const testPassword = 'local-consumer-test-only';
    const traceparent = '00-11111111111111111111111111111111-2222222222222222-01';

    async function management<T>(method: string, path: string, body?: unknown): Promise<T> {
        const response = await fetch(new URL('/api' + path, managementUrl), {
            method,
            headers: {
                Authorization:
                    'Basic ' +
                    Buffer.from(
                        `${decodeURIComponent(brokerAdminUri.username)}:${decodeURIComponent(brokerAdminUri.password)}`,
                    ).toString('base64'),
                'Content-Type': 'application/json',
            },
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Test broker management failed: ${response.status}`);
        return (
            response.status === 204 || response.headers.get('content-length') === '0'
                ? undefined
                : await response.json()
        ) as T;
    }

    function uriFor(user: string): string {
        const uri = new URL(brokerAdminUri);
        uri.username = user;
        uri.password = testPassword;
        uri.pathname = '/' + vhost;
        return uri.toString();
    }

    async function until(check: () => Promise<boolean> | boolean, timeout = 12000): Promise<void> {
        const end = Date.now() + timeout;
        while (Date.now() < end) {
            if (await check()) return;
            await new Promise((resolve) => setTimeout(resolve, 25));
        }
        throw new Error('Timed out waiting for the real integration outcome');
    }

    beforeAll(async () => {
        const db = new URL(process.env.PROFILE_TEST_DATABASE_URL ?? '');
        brokerAdminUri = new URL(process.env.PROFILE_TEST_RABBITMQ_URI ?? '');
        managementUrl = new URL(process.env.PROFILE_TEST_RABBITMQ_MANAGEMENT_URL ?? 'http://127.0.0.1:15679');
        if (
            process.env.PROFILE_INTEGRATION_LOCAL !== 'true' ||
            [db, brokerAdminUri, managementUrl].some((url) => !['localhost', '127.0.0.1'].includes(url.hostname))
        ) {
            throw new Error('Use explicitly authorized local disposable integration infrastructure');
        }
        process.env.APP_ENV = 'test';
        process.env.LOG_LEVEL = 'ERROR';
        process.env.DB_HOST = db.hostname;
        process.env.DB_PORT = db.port || '5432';
        process.env.DB_USER = decodeURIComponent(db.username);
        process.env.DB_PASSWORD = decodeURIComponent(db.password) || 'test-only';
        process.env.DB_NAME = databaseName;
        process.env.DB_SSL = 'false';
        adminDatabase = new DataSource({ type: 'postgres', url: db.toString(), synchronize: false });
        await adminDatabase.initialize();
        await adminDatabase.query(`CREATE DATABASE "${databaseName}"`);
        database = new DataSource(createDatabaseOptions());
        await database.initialize();
        await database.runMigrations();
    });

    beforeEach(async () => {
        vhost = `profile_test_${randomUUID().replaceAll('-', '')}`;
        consumerUser = vhost + '_consumer';
        publisherUser = vhost + '_publisher';
        consumerConnections.length = 0;
        afterCommit = undefined;
        provisions = 0;
        await management('PUT', `/vhosts/${vhost}`, {});
        await management('PUT', `/permissions/${vhost}/${decodeURIComponent(brokerAdminUri.username)}`, {
            configure: '.*',
            write: '.*',
            read: '.*',
        });
        for (const [user, permissions] of [
            [consumerUser, topology.consumerPermissions],
            [publisherUser, { configure: '^identity\\.events$', write: '^identity\\.events$', read: '^$' }],
        ] as const) {
            await management('PUT', `/users/${user}`, { password: testPassword, tags: '' });
            await management('PUT', `/permissions/${vhost}/${user}`, permissions);
        }
        const adminUri = new URL(brokerAdminUri);
        adminUri.pathname = '/' + vhost;
        adminConnection = await connect(adminUri.toString());
        adminConnection.on('error', () => undefined);
        channel = await adminConnection.createConfirmChannel();
        channel.on('error', () => undefined);
        await channel.assertExchange(topology.exchange, 'topic', { durable: true });
        await declareProfileTopology(channel, [100, 250]);
        config = validateEnvironment({
            ...process.env,
            RABBITMQ_URI: uriFor(consumerUser),
            RABBITMQ_URL: undefined,
            RABBITMQ_CONSUMER_ENABLED: true,
            RABBITMQ_RETRY_DELAY_1_MS: 100,
            RABBITMQ_RETRY_DELAY_2_MS: 250,
        });
    });

    afterEach(async () => {
        await listener?.beforeApplicationShutdown();
        listener = undefined;
        await adminConnection?.close().catch(() => undefined);
        if (vhost) await management('DELETE', `/vhosts/${vhost}`);
        if (consumerUser) await management('DELETE', `/users/${consumerUser}`);
        if (publisherUser) await management('DELETE', `/users/${publisherUser}`);
    });

    afterAll(async () => {
        if (database?.isInitialized) await database.destroy();
        if (adminDatabase?.isInitialized) {
            if (!/^profile_test_[a-f0-9]{32}$/.test(databaseName)) throw new Error('Unsafe test database name');
            await adminDatabase.query(`DROP DATABASE IF EXISTS "${databaseName}" WITH (FORCE)`);
            await adminDatabase.destroy();
        }
    });

    async function startConsumer(): Promise<void> {
        const adapter = new TypeormProfileProvisioningAdapter(database);
        const service = new CreateMinimumProfileService({
            provision: async (input) => {
                provisions++;
                const result = await adapter.provision(input);
                await afterCommit?.(input, result);
                return result;
            },
        });
        const logger = new JsonLogger();
        listener = new RabbitMqListener(
            new ConfigService(config),
            {
                connect: async (uri, options) => {
                    const connection = await connect(uri, options);
                    consumerConnections.push(connection);
                    return connection;
                },
            },
            new UserRegisteredConsumer(service, logger),
            logger,
            new TraceContextService(),
        );
        listener.onApplicationBootstrap();
        await until(() => listener!.isReady);
    }

    async function publish(body: unknown, headers: Record<string, unknown> = {}): Promise<void> {
        const message = registrationMessage(body, { traceparent, ...headers });
        await confirmedHandoff(channel, message, topology.exchange, topology.routingKey, {});
    }

    async function nextDeadLetter(timeout = 12000): Promise<GetMessage> {
        let message: GetMessage | false = false;
        await until(async () => {
            message = await channel.get(topology.dlq, { noAck: true });
            return message !== false;
        }, timeout);
        if (!message) throw new Error('Expected a dead letter');
        return message;
    }

    async function installFailure(eventId: string, failures: number, code = '40001'): Promise<string> {
        const name = 'fault_' + randomUUID().replaceAll('-', '');
        await database.query(`CREATE SEQUENCE app.${name}`);
        await database.query(`CREATE FUNCTION app.${name}() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.event_id = '${eventId}'::uuid AND nextval('app.${name}') <= ${failures} THEN
                    RAISE EXCEPTION 'Synthetic local integration failure' USING ERRCODE = '${code}';
                END IF;
                RETURN NEW;
            END $$`);
        await database.query(`CREATE TRIGGER ${name} BEFORE INSERT ON app.inbox_messages
            FOR EACH ROW EXECUTE FUNCTION app.${name}()`);
        return name;
    }

    it('consumes the actual Auth producer event and publication, creating one PENDING profile', async () => {
        await startConsumer();
        const source = registrationEvent();
        const event = createRegistrationEvent({
            id: source.eventId,
            aggregateId: source.aggregateId,
            aggregateVersion: 1,
            occurredAt: new Date(source.occurredAt),
            data: source.data,
        });
        const publisher = new RabbitMqRegistrationEventPublisher(
            new AuthConfigService({ RABBITMQ_URL: uriFor(publisherUser) }),
            { connect },
        );
        try {
            await publisher.publish(event, traceparent);
            await until(
                async () => await database.getRepository(ProfileEntity).existsBy({ userId: event.data.userId }),
            );
            expect(
                await database.getRepository(ProfileEntity).findOneByOrFail({ userId: event.data.userId }),
            ).toMatchObject({
                contactEmail: source.data.initialContactEmail,
                name: null,
                phone: null,
                onboardingStatus: OnboardingStatus.PENDING,
            });
            expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: event.eventId })).toBe(1);
            await publisher.publish(event, traceparent);
            await until(() => provisions === 2);
            expect(await database.getRepository(ProfileEntity).countBy({ userId: event.data.userId })).toBe(1);
        } finally {
            await publisher.onApplicationShutdown();
        }
    });

    it('keeps the delivery unacknowledged and inbox invisible while the transaction is blocked', async () => {
        await startConsumer();
        const event = registrationEvent();
        const blocker = database.createQueryRunner();
        try {
            await blocker.startTransaction();
            await blocker.query('LOCK TABLE app.profile IN ACCESS EXCLUSIVE MODE');
            await publish(event);
            await until(async () => {
                const state = await management<{ messages_unacknowledged: number }>(
                    'GET',
                    `/queues/${vhost}/${topology.queue}`,
                );
                return state.messages_unacknowledged === 1;
            });
            expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: event.eventId })).toBe(0);
            await blocker.commitTransaction();
            await until(
                async () => await database.getRepository(ProfileEntity).existsBy({ userId: event.data.userId }),
            );
            await until(async () => {
                const state = await management<{ messages: number }>('GET', `/queues/${vhost}/${topology.queue}`);
                return state.messages === 0;
            });
        } finally {
            if (blocker.isTransactionActive) await blocker.rollbackTransaction();
            await blocker.release();
        }
    });

    it('sends invalid contracts to DLQ without persisting or exposing their contents in errors', async () => {
        await startConsumer();
        const invalid = { ...registrationEvent(), schemaVersion: 2 };
        await publish(invalid);
        const dead = await nextDeadLetter();
        expect(dead.content).toEqual(Buffer.from(JSON.stringify(invalid)));
        expect(dead.properties.headers?.['x-profile-failure-code']).toBe('REGISTRATION_EVENT_INVALID');
        expect(provisions).toBe(0);
    });

    it('rolls back failed transactions and succeeds on the third scheduled attempt', async () => {
        const event = registrationEvent();
        const sequence = await installFailure(event.eventId, 2);
        await startConsumer();
        await publish(event);
        await until(async () => await database.getRepository(ProfileEntity).existsBy({ userId: event.data.userId }));
        const counts = await database.query<Array<{ last_value: string }>>(`SELECT last_value FROM app.${sequence}`);
        expect(Number(counts[0].last_value)).toBe(3);
        expect(provisions).toBe(3);
        expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: event.eventId })).toBe(1);
    });

    it('exhausts exactly three attempts before DLQ and leaves no processed inbox row', async () => {
        const event = registrationEvent();
        await installFailure(event.eventId, 10);
        await startConsumer();
        await publish(event);
        const dead = await nextDeadLetter();
        expect(dead.properties.headers?.['x-profile-attempt']).toBe(3);
        expect(dead.properties.headers?.['x-profile-failure-code']).toBe('REGISTRATION_RETRIES_EXHAUSTED');
        expect(provisions).toBe(3);
        expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: event.eventId })).toBe(0);
        expect(await database.getRepository(ProfileEntity).countBy({ userId: event.data.userId })).toBe(0);
    });

    it('dead-letters a permanent database rejection without retrying', async () => {
        const event = registrationEvent();
        await installFailure(event.eventId, 10, '23514');
        await startConsumer();
        await publish(event);
        expect((await nextDeadLetter()).properties.headers?.['x-profile-failure-code']).toBe(
            'REGISTRATION_PERSISTENCE_REJECTED',
        );
        expect(provisions).toBe(1);
    });

    it('preserves an unrouted DLQ message and recovers by redelivery after reconnect', async () => {
        await startConsumer();
        await channel.unbindQueue(topology.dlq, topology.deadLetterExchange, topology.deadLetterRoutingKey);
        await publish({ schemaVersion: 99 });
        await until(() => !listener!.isReady);
        await until(async () => (await channel.checkQueue(topology.queue)).messageCount === 1);
        expect((await nextDeadLetter()).content.toString()).toBe(JSON.stringify({ schemaVersion: 99 }));
        await until(() => listener!.isReady);
    });

    it('retains expired retries when the return route is absent and delivers when it is restored', async () => {
        await channel.unbindQueue(topology.queue, topology.retryExchange, 'ready');
        const message = registrationMessage(registrationEvent());
        await confirmedHandoff(channel, message, topology.retryExchange, topology.retries[0].routingKey, {
            'x-profile-attempt': 2,
        });
        await new Promise((resolve) => setTimeout(resolve, 400));
        const retry = await management<{ messages: number; arguments: Record<string, unknown> }>(
            'GET',
            `/queues/${vhost}/${topology.retries[0].queue}`,
        );
        expect(retry.arguments['x-dead-letter-strategy']).toBe('at-least-once');
        await channel.bindQueue(topology.queue, topology.retryExchange, 'ready');
        let returned: GetMessage | false = false;
        await until(async () => {
            returned = await channel.get(topology.queue, { noAck: true });
            return returned !== false;
        }, 45000);
        if (!returned) throw new Error('Retry was lost');
        expect((returned as GetMessage).content).toEqual(message.content);
    }, 60000);

    it('handles connection loss after commit without reverting an edited COMPLETED profile', async () => {
        const event = registrationEvent();
        let before: ProfileEntity | undefined;
        afterCommit = async (input, result) => {
            if (input.eventId !== event.eventId || result.status !== 'processed') return;
            await database.getRepository(ProfileEntity).update(
                { userId: input.userId },
                {
                    name: 'Completed Customer',
                    phone: '5551234567',
                    contactEmail: 'changed@example.com',
                    onboardingStatus: OnboardingStatus.COMPLETED,
                },
            );
            before = await database.getRepository(ProfileEntity).findOneByOrFail({ userId: input.userId });
            await consumerConnections[0].close();
        };
        await startConsumer();
        await publish(event);
        await until(() => provisions >= 2);
        expect(await database.getRepository(ProfileEntity).findOneByOrFail({ userId: event.data.userId })).toEqual(
            before,
        );
        expect(await database.getRepository(InboxMessageEntity).countBy({ eventId: event.eventId })).toBe(1);
    });

    it('lets Profile declare and consume its topology but rejects identity publication', async () => {
        await startConsumer();
        const connection = await connect(uriFor(consumerUser));
        connection.on('error', () => undefined);
        const denied = await connection.createConfirmChannel();
        denied.on('error', () => undefined);
        try {
            await expect(
                confirmedHandoff(denied, registrationMessage(), topology.exchange, topology.routingKey, {}),
            ).rejects.toThrow('REGISTRATION_HANDOFF_FAILED');
        } finally {
            await connection.close().catch(() => undefined);
        }
    });

    it('boots the real AppModule, consumes with its injected adapter and closes cleanly', async () => {
        process.env.RABBITMQ_URI = uriFor(consumerUser);
        process.env.RABBITMQ_RETRY_DELAY_1_MS = '100';
        process.env.RABBITMQ_RETRY_DELAY_2_MS = '250';
        const { AppModule } = await import('../src/app.module.js');
        const appDatabase = new DataSource(database.options);
        await appDatabase.initialize();
        const fixture = await Test.createTestingModule({ imports: [AppModule] })
            .overrideProvider(DataSource)
            .useValue(appDatabase)
            .compile();
        const app = fixture.createNestApplication();
        app.useLogger(false);
        try {
            await app.init();
            await until(() => app.get(RabbitMqListener).isReady);
            const event = registrationEvent();
            await publish(event);
            await until(
                async () => await database.getRepository(ProfileEntity).existsBy({ userId: event.data.userId }),
            );
            await request(app.getHttpServer() as Parameters<typeof request>[0])
                .get('/health/ready')
                .expect(200);
        } finally {
            await app.close();
        }
        expect(appDatabase.isInitialized).toBe(false);
        expect(app.get(RabbitMqListener).isReady).toBe(false);
    });
});
