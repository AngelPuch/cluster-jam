import type { RegistrationEvent } from '../events/registration-event';

export const REGISTRATION_EVENT_PUBLISHER_PORT = Symbol(
    'REGISTRATION_EVENT_PUBLISHER_PORT',
);

export interface RegistrationEventPublisherPort {
    publish(event: RegistrationEvent, traceparent: string): Promise<void>;
}
