import 'reflect-metadata';
import { plainToInstance, Type } from 'class-transformer';
import {
    Equals,
    IsDefined,
    IsEmail,
    IsISO8601,
    IsObject,
    IsUUID,
    Matches,
    MaxLength,
    ValidateNested,
    validateSync,
} from 'class-validator';
import type { ConsumeMessage } from 'amqplib';

class RegistrationDataDto {
    @IsUUID()
    userId!: string;

    @IsEmail()
    @MaxLength(254)
    initialContactEmail!: string;
}

export class UserRegisteredEventDto {
    @IsUUID()
    eventId!: string;

    @Equals('identity.user.registered')
    eventType!: 'identity.user.registered';

    @Equals(1)
    schemaVersion!: 1;

    @IsUUID()
    aggregateId!: string;

    @Equals(1)
    aggregateVersion!: 1;

    @IsISO8601({ strict: true, strictSeparator: true })
    @Matches(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/)
    @MaxLength(50)
    occurredAt!: string;

    @IsDefined()
    @IsObject()
    @ValidateNested()
    @Type(() => RegistrationDataDto)
    data!: RegistrationDataDto;
}

export class InvalidRegistrationMessage extends Error {
    constructor() {
        super('REGISTRATION_EVENT_INVALID');
    }
}

function hasOnlyKeys(value: unknown, keys: string[]): value is Record<string, unknown> {
    return (
        typeof value === 'object' &&
        value !== null &&
        !Array.isArray(value) &&
        Object.keys(value).every((key) => keys.includes(key))
    );
}

export function parseRegistrationMessage(message: ConsumeMessage): UserRegisteredEventDto {
    try {
        if (message.content.length > 65536) throw new InvalidRegistrationMessage();
        const input: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(message.content));
        if (
            !hasOnlyKeys(input, [
                'eventId',
                'eventType',
                'schemaVersion',
                'aggregateId',
                'aggregateVersion',
                'occurredAt',
                'data',
            ]) ||
            !hasOnlyKeys(input.data, ['userId', 'initialContactEmail'])
        )
            throw new InvalidRegistrationMessage();
        const event = plainToInstance(UserRegisteredEventDto, input);
        if (
            validateSync(event, {
                whitelist: true,
                forbidNonWhitelisted: true,
                forbidUnknownValues: true,
                validationError: { target: false, value: false },
            }).length > 0 ||
            event.aggregateId.toLowerCase() !== event.data.userId.toLowerCase()
        ) {
            throw new InvalidRegistrationMessage();
        }
        const properties: { readonly [K in keyof ConsumeMessage['properties']]: unknown } = message.properties;
        if (
            (properties.messageId !== undefined && properties.messageId !== event.eventId) ||
            (properties.type !== undefined && properties.type !== event.eventType) ||
            (properties.contentType !== undefined && properties.contentType !== 'application/json') ||
            (properties.contentEncoding !== undefined &&
                (typeof properties.contentEncoding !== 'string' ||
                    properties.contentEncoding.toLowerCase() !== 'utf-8')) ||
            (message.properties.headers?.schemaVersion !== undefined && message.properties.headers.schemaVersion !== 1)
        ) {
            throw new InvalidRegistrationMessage();
        }
        return event;
    } catch {
        throw new InvalidRegistrationMessage();
    }
}
