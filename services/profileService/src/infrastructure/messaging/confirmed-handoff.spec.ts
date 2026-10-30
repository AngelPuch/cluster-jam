import { EventEmitter } from 'node:events';
import type { ConfirmChannel, Options } from 'amqplib';
import { confirmedHandoff } from './confirmed-handoff';
import { registrationMessage } from '../../../test/helpers/registration.fixture';

describe('Confirmed retry/DLQ handoff', () => {
    function channelWith(
        action: (channel: EventEmitter, options: Options.Publish, confirm: (error?: Error) => void) => void,
    ) {
        const channel = new EventEmitter();
        const publish = (
            _exchange: string,
            _key: string,
            _body: Buffer,
            options: Options.Publish,
            confirm: (error?: Error) => void,
        ) => {
            action(channel, options, confirm);
            return true;
        };
        return Object.assign(channel, { publish }) as unknown as ConfirmChannel;
    }

    it('uses persistent mandatory publication and preserves the body, identifiers and trace headers', async () => {
        const message = registrationMessage(undefined, { traceparent: '00-trace-parent-01' });
        message.properties.expiration = '1';
        const channel = channelWith((_channel, options, confirm) => {
            expect(options).toMatchObject({
                persistent: true,
                mandatory: true,
                messageId: expect.any(String) as string,
                headers: { 'x-profile-attempt': 2, traceparent: '00-trace-parent-01' },
            });
            expect(options.expiration).toBeUndefined();
            confirm();
        });
        await confirmedHandoff(channel, message, 'retry', 'attempt.2', { 'x-profile-attempt': 2 });
        expect(channel.listenerCount('return')).toBe(0);
        expect(channel.listenerCount('close')).toBe(0);
    });

    it('treats an unroutable return as failure even when the broker confirms', async () => {
        const channel = channelWith((emitter, _options, confirm) => {
            emitter.emit('return');
            confirm();
        });
        await expect(confirmedHandoff(channel, registrationMessage(), 'missing-route', 'key', {})).rejects.toThrow(
            'REGISTRATION_HANDOFF_FAILED',
        );
    });

    it('rejects a broker NACK', async () => {
        const channel = channelWith((_emitter, _options, confirm) => confirm(new Error('nack')));
        await expect(confirmedHandoff(channel, registrationMessage(), 'retry', 'key', {})).rejects.toThrow(
            'REGISTRATION_HANDOFF_FAILED',
        );
    });

    it('rejects connection loss while waiting for confirmation', async () => {
        const channel = channelWith((emitter) => {
            emitter.emit('close');
        });
        await expect(confirmedHandoff(channel, registrationMessage(), 'retry', 'key', {})).rejects.toThrow(
            'REGISTRATION_HANDOFF_FAILED',
        );
    });

    it('times out an uncertain publication and removes its listeners', async () => {
        const channel = channelWith(() => undefined);
        await expect(confirmedHandoff(channel, registrationMessage(), 'retry', 'key', {}, 5)).rejects.toThrow(
            'REGISTRATION_HANDOFF_FAILED',
        );
        expect(channel.listenerCount('return')).toBe(0);
        expect(channel.listenerCount('close')).toBe(0);
    });
});
