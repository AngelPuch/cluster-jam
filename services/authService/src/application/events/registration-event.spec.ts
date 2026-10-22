import { describe, expect, it } from '@jest/globals';
import {
    createRegistrationEvent,
    type RegistrationOutboxRecord,
} from './registration-event';

const record: RegistrationOutboxRecord = {
    id: '11111111-1111-4111-8111-111111111111',
    aggregateId: '22222222-2222-4222-8222-222222222222',
    aggregateVersion: 1,
    occurredAt: new Date('2026-10-20T12:00:00Z'),
    data: {
        userId: '22222222-2222-4222-8222-222222222222',
        initialContactEmail: 'user@example.com',
    },
};

describe('Registration event contract', () => {
    it('preserves event identity and strips fields outside the allowlist', () => {
        const event = createRegistrationEvent({
            ...record,
            data: {
                ...(record.data as object),
                password: 'private-password',
                refreshToken: 'private-token',
            },
        });
        expect(event).toEqual({
            eventId: record.id,
            eventType: 'identity.user.registered',
            schemaVersion: 1,
            aggregateId: record.aggregateId,
            aggregateVersion: 1,
            occurredAt: '2026-10-20T12:00:00.000Z',
            data: {
                userId: record.aggregateId,
                initialContactEmail: 'user@example.com',
            },
        });
        expect(JSON.stringify(event)).not.toContain('private-');
    });

    it.each([
        null,
        [],
        {},
        { userId: record.id, initialContactEmail: 'user@example.com' },
        { userId: record.aggregateId, initialContactEmail: 'invalid-email' },
    ])('rejects invalid payload %#', (data) => {
        expect(() => createRegistrationEvent({ ...record, data })).toThrow(
            'REGISTRATION_EVENT_INVALID',
        );
    });

    it('rejects an incompatible aggregate version', () => {
        expect(() =>
            createRegistrationEvent({ ...record, aggregateVersion: 2 }),
        ).toThrow('REGISTRATION_EVENT_INVALID');
    });
});
