import { isEmail, isUUID } from 'class-validator';

export const REGISTRATION_EXCHANGE = 'identity.events';
export const REGISTRATION_ROUTING_KEY = 'identity.user.registered.v1';

export interface RegistrationOutboxRecord {
    id: string;
    aggregateId: string;
    aggregateVersion: number;
    occurredAt: Date;
    data: unknown;
}

export interface RegistrationEvent {
    eventId: string;
    eventType: 'identity.user.registered';
    schemaVersion: 1;
    aggregateId: string;
    aggregateVersion: 1;
    occurredAt: string;
    data: { userId: string; initialContactEmail: string };
}

export class RegistrationPublicationError extends Error {
    constructor(public readonly code: string) {
        super(code);
        this.name = 'RegistrationPublicationError';
    }
}

export function createRegistrationEvent(
    row: RegistrationOutboxRecord,
): RegistrationEvent {
    const data = row.data as Record<string, unknown> | null;
    if (
        !isUUID(row.id) ||
        !isUUID(row.aggregateId) ||
        row.aggregateVersion !== 1 ||
        !(row.occurredAt instanceof Date) ||
        !Number.isFinite(row.occurredAt.getTime()) ||
        typeof data !== 'object' ||
        data === null ||
        Array.isArray(data) ||
        data.userId !== row.aggregateId ||
        typeof data.initialContactEmail !== 'string' ||
        data.initialContactEmail.length > 254 ||
        !isEmail(data.initialContactEmail)
    ) {
        throw new RegistrationPublicationError('REGISTRATION_EVENT_INVALID');
    }

    return {
        eventId: row.id,
        eventType: 'identity.user.registered',
        schemaVersion: 1,
        aggregateId: row.aggregateId,
        aggregateVersion: 1,
        occurredAt: row.occurredAt.toISOString(),
        data: {
            userId: row.aggregateId,
            initialContactEmail: data.initialContactEmail,
        },
    };
}
