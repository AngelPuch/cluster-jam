import { jest } from '@jest/globals';
import { CreateMinimumProfileService } from '../../application/profile/create-minimum-profile.service';
import type {
    ProfileProvisioningPort,
    ProfileProvisioningResult,
} from '../../application/ports/profile-provisioning.port';
import { JsonLogger } from '../../infrastructure/observability/json-logger.service';
import { UserRegisteredConsumer, type RegistrationDelivery } from './user-registered.consumer';
import { registrationEvent, registrationMessage } from '../../../test/helpers/registration.fixture';

describe('Registration consumer acknowledgement and retries', () => {
    const provision = jest.fn<ProfileProvisioningPort['provision']>();
    const logger = new JsonLogger();
    const consumer = new UserRegisteredConsumer(new CreateMinimumProfileService({ provision }), logger);
    let delivery: jest.Mocked<RegistrationDelivery>;

    beforeEach(() => {
        provision.mockReset().mockResolvedValue({ status: 'processed', profileCreated: true });
        delivery = {
            ack: jest.fn(),
            retry: jest.fn<RegistrationDelivery['retry']>().mockResolvedValue(),
            deadLetter: jest.fn<RegistrationDelivery['deadLetter']>().mockResolvedValue(),
        };
        jest.spyOn(logger, 'warn').mockImplementation(() => undefined);
        jest.spyOn(logger, 'debug').mockImplementation(() => undefined);
    });
    afterEach(() => jest.restoreAllMocks());

    it('does not acknowledge until the transaction Promise completes', async () => {
        let commit!: (result: ProfileProvisioningResult) => void;
        provision.mockImplementation(
            () =>
                new Promise((resolve) => {
                    commit = resolve;
                }),
        );
        const event = registrationEvent();
        const handling = consumer.handle(registrationMessage(event), delivery);
        expect(delivery.ack).not.toHaveBeenCalled();
        commit({ status: 'processed', profileCreated: true });
        await handling;
        expect(delivery.ack).toHaveBeenCalledTimes(1);
        expect(provision).toHaveBeenCalledWith({
            eventId: event.eventId,
            userId: event.data.userId,
            initialContactEmail: event.data.initialContactEmail,
        });
    });

    it('acknowledges duplicates normally', async () => {
        provision.mockResolvedValue({ status: 'duplicate' });
        await consumer.handle(registrationMessage(), delivery);
        expect(delivery.ack).toHaveBeenCalledTimes(1);
        expect(delivery.retry).not.toHaveBeenCalled();
    });

    it.each([{}, { 'x-profile-attempt': 0 }, { 'x-profile-attempt': 4 }, { 'x-profile-attempt': '2' }])(
        'dead-letters invalid contracts/attempts without touching persistence: %j',
        async (headers) => {
            const message = registrationMessage(Object.keys(headers).length === 0 ? {} : registrationEvent(), headers);
            await consumer.handle(message, delivery);
            expect(provision).not.toHaveBeenCalled();
            expect(delivery.deadLetter).toHaveBeenCalledWith('REGISTRATION_EVENT_INVALID');
            expect(delivery.ack).toHaveBeenCalledTimes(1);
        },
    );

    it.each([1, 2])('retries transient attempt %s only after a guaranteed handoff', async (attempt) => {
        provision.mockRejectedValue({ driverError: { code: '40001' } });
        let confirm!: () => void;
        delivery.retry.mockImplementation(
            () =>
                new Promise((resolve) => {
                    confirm = resolve;
                }),
        );
        const handling = consumer.handle(
            registrationMessage(registrationEvent(), { 'x-profile-attempt': attempt }),
            delivery,
        );
        await Promise.resolve();
        expect(delivery.ack).not.toHaveBeenCalled();
        expect(delivery.retry).toHaveBeenCalledWith(attempt + 1);
        confirm();
        await handling;
        expect(delivery.ack).toHaveBeenCalledTimes(1);
    });

    it('moves the third transient attempt to DLQ without a fourth attempt', async () => {
        provision.mockRejectedValue({ code: 'ECONNRESET' });
        await consumer.handle(registrationMessage(registrationEvent(), { 'x-profile-attempt': 3 }), delivery);
        expect(delivery.deadLetter).toHaveBeenCalledWith('REGISTRATION_RETRIES_EXHAUSTED');
        expect(delivery.retry).not.toHaveBeenCalled();
        expect(delivery.ack).toHaveBeenCalledTimes(1);
    });

    it('retries a pg pool connection error without an exposed SQLSTATE', async () => {
        provision.mockRejectedValue(new Error('Connection terminated due to connection timeout'));
        await consumer.handle(registrationMessage(), delivery);
        expect(delivery.retry).toHaveBeenCalledWith(2);
        expect(delivery.deadLetter).not.toHaveBeenCalled();
    });

    it('dead-letters permanent persistence failures', async () => {
        provision.mockRejectedValue({ driverError: { code: '23514' } });
        await consumer.handle(registrationMessage(), delivery);
        expect(delivery.deadLetter).toHaveBeenCalledWith('REGISTRATION_PERSISTENCE_REJECTED');
    });

    it('leaves the original unacknowledged if retry publication fails', async () => {
        provision.mockRejectedValue({ code: 'ECONNREFUSED' });
        delivery.retry.mockRejectedValue(new Error('handoff failed'));
        await expect(consumer.handle(registrationMessage(), delivery)).rejects.toThrow('handoff failed');
        expect(delivery.ack).not.toHaveBeenCalled();
    });

    it('leaves invalid input unacknowledged if DLQ publication fails', async () => {
        delivery.deadLetter.mockRejectedValue(new Error('handoff failed'));
        await expect(consumer.handle(registrationMessage({}), delivery)).rejects.toThrow('handoff failed');
        expect(delivery.ack).not.toHaveBeenCalled();
    });
});
