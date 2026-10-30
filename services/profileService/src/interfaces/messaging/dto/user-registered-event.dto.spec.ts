import { parseRegistrationMessage } from './user-registered-event.dto';
import { registrationEvent, registrationMessage } from '../../../../test/helpers/registration.fixture';

describe('Registration event contract', () => {
    it('accepts every required field from the versioned Auth event', () => {
        const event = registrationEvent();
        expect(parseRegistrationMessage(registrationMessage(event))).toEqual(event);
    });

    it.each(['eventId', 'eventType', 'schemaVersion', 'aggregateId', 'aggregateVersion', 'occurredAt', 'data'])(
        'rejects a missing %s',
        (key) => {
            const event: Record<string, unknown> = registrationEvent();
            delete event[key];
            expect(() => parseRegistrationMessage(registrationMessage(event))).toThrow('REGISTRATION_EVENT_INVALID');
        },
    );

    it.each([
        { schemaVersion: 2 },
        { schemaVersion: '1' },
        { aggregateVersion: 2 },
        { eventType: 'identity.other' },
        { eventId: 'not-a-uuid' },
        { aggregateId: 'not-a-uuid' },
        { occurredAt: '2026-10-29' },
        { occurredAt: '2026-02-30T12:00:00Z' },
        { occurredAt: '2026-10-29T12:00:00' },
        { password: 'must-not-pass' },
        { data: [] },
        { data: null },
    ])('rejects malformed payload %j', (changes) => {
        expect(() => parseRegistrationMessage(registrationMessage({ ...registrationEvent(), ...changes }))).toThrow(
            'REGISTRATION_EVENT_INVALID',
        );
    });

    it.each([
        { userId: 'invalid' },
        { initialContactEmail: 'invalid' },
        { initialContactEmail: 'x'.repeat(255) + '@example.com' },
        { refreshToken: 'must-not-pass' },
    ])('rejects malformed registration data %j', (changes) => {
        const event = registrationEvent();
        expect(() =>
            parseRegistrationMessage(registrationMessage({ ...event, data: { ...event.data, ...changes } })),
        ).toThrow('REGISTRATION_EVENT_INVALID');
    });

    it('rejects a different aggregate identity', () => {
        const event = registrationEvent();
        event.aggregateId = registrationEvent().aggregateId;
        expect(() => parseRegistrationMessage(registrationMessage(event))).toThrow('REGISTRATION_EVENT_INVALID');
    });

    it.each([Buffer.from('{broken'), Buffer.from([0xff]), Buffer.alloc(65537), 'plain string', null])(
        'rejects invalid JSON, encoding, size and root types without leaking content',
        (content) => {
            expect(() => parseRegistrationMessage(registrationMessage(content))).toThrow('REGISTRATION_EVENT_INVALID');
        },
    );

    it('rejects conflicting AMQP metadata', () => {
        for (const key of ['messageId', 'type', 'contentType', 'contentEncoding'] as const) {
            const message = registrationMessage();
            message.properties[key] = 'invalid';
            expect(() => parseRegistrationMessage(message)).toThrow('REGISTRATION_EVENT_INVALID');
        }
        expect(() => parseRegistrationMessage(registrationMessage(registrationEvent(), { schemaVersion: 2 }))).toThrow(
            'REGISTRATION_EVENT_INVALID',
        );
    });
});
