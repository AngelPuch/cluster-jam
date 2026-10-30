import { Injectable } from '@nestjs/common';
import type { ConsumeMessage } from 'amqplib';
import { CreateMinimumProfileService } from '../../application/profile/create-minimum-profile.service';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { parseRegistrationMessage } from './dto/user-registered-event.dto';

export interface RegistrationDelivery {
    ack: () => void;
    retry: (attempt: number) => Promise<void>;
    deadLetter: (reason: string) => Promise<void>;
}

function isTransient(error: unknown): boolean {
    if (typeof error !== 'object' || error === null) return false;
    const outer = error as { code?: unknown; driverError?: { code?: unknown } };
    const code = outer.driverError?.code ?? outer.code;
    // Some pg pool connection timeouts are Error instances without a code.
    // Retry opaque failures finitely rather than misclassifying an outage.
    if (code === undefined && error instanceof Error) return true;
    return (
        typeof code === 'string' &&
        (code.startsWith('08') ||
            [
                '40001',
                '40P01',
                '53300',
                '57P01',
                '57P02',
                '57P03',
                '55P03',
                '57014',
                'ECONNRESET',
                'ECONNREFUSED',
                'ETIMEDOUT',
                'EPIPE',
                'ENETUNREACH',
                'EHOSTUNREACH',
            ].includes(code))
    );
}

@Injectable()
export class UserRegisteredConsumer {
    constructor(
        private readonly profiles: CreateMinimumProfileService,
        private readonly logger: JsonLogger,
    ) {}

    async handle(message: ConsumeMessage, delivery: RegistrationDelivery): Promise<void> {
        let event: ReturnType<typeof parseRegistrationMessage>;
        const attempt: unknown = message.properties.headers?.['x-profile-attempt'] ?? 1;
        try {
            if (typeof attempt !== 'number' || !Number.isSafeInteger(attempt) || attempt < 1 || attempt > 3) {
                throw new Error('REGISTRATION_ATTEMPT_INVALID');
            }
            event = parseRegistrationMessage(message);
        } catch {
            await delivery.deadLetter('REGISTRATION_EVENT_INVALID');
            delivery.ack();
            this.logger.warn({ event: 'profile.event.dead-lettered', code: 'REGISTRATION_EVENT_INVALID' });
            return;
        }
        let result: Awaited<ReturnType<CreateMinimumProfileService['execute']>>;
        try {
            result = await this.profiles.execute({
                eventId: event.eventId,
                userId: event.data.userId,
                initialContactEmail: event.data.initialContactEmail,
            });
        } catch (error) {
            if (isTransient(error) && attempt < 3) {
                await delivery.retry(attempt + 1);
                delivery.ack();
                this.logger.debug({ event: 'profile.event.retry', event_id: event.eventId, attempt });
            } else {
                const code = isTransient(error)
                    ? 'REGISTRATION_RETRIES_EXHAUSTED'
                    : 'REGISTRATION_PERSISTENCE_REJECTED';
                await delivery.deadLetter(code);
                delivery.ack();
                this.logger.warn({ event: 'profile.event.dead-lettered', event_id: event.eventId, code, attempt });
            }
            return;
        }
        delivery.ack();
        this.logger.debug({
            event: 'profile.event.processed',
            event_id: event.eventId,
            aggregate_id: event.data.userId,
            duplicate: result.status === 'duplicate',
            attempt,
        });
    }
}
