import type { RegistrationOutboxRecord } from '../events/registration-event';

export const REGISTRATION_OUTBOX_PORT = Symbol('REGISTRATION_OUTBOX_PORT');

export type OutboxDeliveryResult =
    | { status: 'empty' }
    | { status: 'published' }
    | { status: 'retry'; code: string };

export interface RegistrationOutboxPort {
    deliverNext(
        deliver: (record: RegistrationOutboxRecord) => Promise<void>,
    ): Promise<OutboxDeliveryResult>;
}
