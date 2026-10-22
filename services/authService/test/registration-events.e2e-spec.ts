import { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { afterAll, beforeAll, describe, expect, it, jest } from '@jest/globals';
import request from 'supertest';
import type { App } from 'supertest/types';

import { AppModule } from '../src/app.module';
import { PublishRegistrationEventsService } from '../src/application/events/publish-registration-events.service';
import {
    RegistrationPublicationError,
    type RegistrationOutboxRecord,
} from '../src/application/events/registration-event';
import {
    REGISTRATION_EVENT_PUBLISHER_PORT,
    type RegistrationEventPublisherPort,
} from '../src/application/ports/registration-event-publisher.port';
import {
    REGISTRATION_OUTBOX_PORT,
    type RegistrationOutboxPort,
} from '../src/application/ports/registration-outbox.port';
import { UserRegistrationStatus } from '../src/application/ports/auth-provider.port';
import { SupabaseAuthAdapter } from '../src/infrastructure/supabase/supabase-auth.adapter';
import { configureHttpApplication } from '../src/interfaces/http/http.setup';

describe('Registration event flow (HTTP e2e with doubles)', () => {
    let app: INestApplication<App>;
    let service: PublishRegistrationEventsService;
    let published = false;
    let pending: RegistrationOutboxRecord | undefined;
    let register: jest.SpiedFunction<SupabaseAuthAdapter['registerUser']>;
    const publish = jest.fn<RegistrationEventPublisherPort['publish']>();
    const outbox: RegistrationOutboxPort = {
        async deliverNext(deliver) {
            if (!pending || published) return { status: 'empty' };
            try {
                await deliver(pending);
                published = true;
                return { status: 'published' };
            } catch {
                return {
                    status: 'retry',
                    code: 'REGISTRATION_PUBLICATION_FAILED',
                };
            }
        },
    };

    beforeAll(async () => {
        register = jest
            .spyOn(SupabaseAuthAdapter.prototype, 'registerUser')
            .mockImplementation((input) => {
                pending = {
                    id: '11111111-1111-4111-8111-111111111111',
                    aggregateId: '22222222-2222-4222-8222-222222222222',
                    aggregateVersion: 1,
                    occurredAt: new Date(),
                    data: {
                        userId: '22222222-2222-4222-8222-222222222222',
                        initialContactEmail: input.email,
                    },
                };
                return Promise.resolve({
                    userId: pending.aggregateId,
                    email: input.email,
                    status: UserRegistrationStatus.PendingEmailConfirmation,
                });
            });
        const module = await Test.createTestingModule({ imports: [AppModule] })
            .overrideProvider(REGISTRATION_OUTBOX_PORT)
            .useValue(outbox)
            .overrideProvider(REGISTRATION_EVENT_PUBLISHER_PORT)
            .useValue({ publish })
            .compile();
        app = module.createNestApplication();
        configureHttpApplication(app);
        await app.init();
        service = app.get(PublishRegistrationEventsService);
    });

    afterAll(async () => {
        register.mockRestore();
        await app.close();
    });

    it('keeps registration asynchronous, retries and preserves eventId', async () => {
        publish.mockRejectedValueOnce(
            new RegistrationPublicationError('REGISTRATION_BROKER_UNAVAILABLE'),
        );
        publish.mockResolvedValue(undefined);
        const response = await request(app.getHttpServer())
            .post('/api/v1/registrations')
            .send({
                email: 'new-user@example.com',
                password: 'StrongPassword123!',
            })
            .expect(201);
        expect(response.body).toMatchObject({
            status: 'PENDING_EMAIL_CONFIRMATION',
        });
        expect(publish).not.toHaveBeenCalled();
        await expect(service.execute(1)).resolves.toEqual({
            published: 0,
            retried: 1,
        });
        expect(published).toBe(false);
        await expect(service.execute(1)).resolves.toEqual({
            published: 1,
            retried: 0,
        });
        expect(published).toBe(true);
        expect(publish.mock.calls[1][0].eventId).toBe(
            publish.mock.calls[0][0].eventId,
        );
        expect(JSON.stringify(publish.mock.calls)).not.toContain(
            'StrongPassword123!',
        );
        await service.execute(1);
        expect(publish).toHaveBeenCalledTimes(2);
    });

    it('keeps the worker private and the existing HTTP contract visible in Swagger', async () => {
        const response = await request(app.getHttpServer())
            .get('/openapi.json')
            .expect(200);
        const document = response.body as { paths: Record<string, unknown> };
        expect(document.paths['/api/v1/registrations']).toBeDefined();
        expect(
            Object.keys(document.paths).some((path) =>
                /outbox|publish-registration-events/.test(path),
            ),
        ).toBe(false);
        await request(app.getHttpServer())
            .post('/api/v1/outbox/publications')
            .send({})
            .expect(404);
    });
});
