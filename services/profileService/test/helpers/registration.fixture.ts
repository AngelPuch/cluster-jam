import { randomUUID } from 'node:crypto';
import type { ConsumeMessage } from 'amqplib';

export function registrationEvent() {
    const userId = randomUUID();
    return {
        eventId: randomUUID(),
        eventType: 'identity.user.registered',
        schemaVersion: 1,
        aggregateId: userId,
        aggregateVersion: 1,
        occurredAt: new Date().toISOString(),
        data: { userId, initialContactEmail: 'customer@example.com' },
    };
}

export function registrationMessage(
    body: unknown = registrationEvent(),
    headers: Record<string, unknown> = {},
): ConsumeMessage {
    const value = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
    return {
        content: Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body)),
        fields: {
            consumerTag: 'test',
            deliveryTag: 1,
            redelivered: false,
            exchange: 'identity.events',
            routingKey: 'identity.user.registered.v1',
        },
        properties: {
            contentType: 'application/json',
            contentEncoding: 'utf-8',
            messageId: typeof value.eventId === 'string' ? value.eventId : undefined,
            type: 'identity.user.registered',
            headers: { schemaVersion: 1, ...headers },
            deliveryMode: 2,
            priority: 0,
            correlationId: undefined,
            replyTo: undefined,
            expiration: undefined,
            timestamp: undefined,
            userId: undefined,
            appId: undefined,
            clusterId: undefined,
        },
    };
}
