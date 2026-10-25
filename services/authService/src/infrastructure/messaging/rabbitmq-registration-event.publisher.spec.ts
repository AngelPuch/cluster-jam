import { ConfigService } from '@nestjs/config';
import { afterEach, beforeEach, describe, expect, it, jest } from '@jest/globals';
import { EventEmitter } from 'node:events';
import type { ChannelModel, ConfirmChannel } from 'amqplib';
import type { RegistrationEvent } from '../../application/events/registration-event';
import {
  RabbitMqRegistrationEventPublisher,
  type AmqpConnector,
} from './rabbitmq-registration-event.publisher';

const event: RegistrationEvent = {
  eventId: '11111111-1111-4111-8111-111111111111',
  eventType: 'identity.user.registered',
  schemaVersion: 1,
  aggregateId: '22222222-2222-4222-8222-222222222222',
  aggregateVersion: 1,
  occurredAt: '2026-10-20T12:00:00.000Z',
  data: {
    userId: '22222222-2222-4222-8222-222222222222',
    initialContactEmail: 'private@example.com',
  },
};

describe('RabbitMqRegistrationEventPublisher', () => {
  let channel: ConfirmChannel;
  let connection: ChannelModel;
  let adapter: RabbitMqRegistrationEventPublisher;
  let connector: AmqpConnector;
  let confirm: (error: unknown) => void;

  beforeEach(() => {
    channel = Object.assign(new EventEmitter(), {
      assertExchange: jest
        .fn<ConfirmChannel['assertExchange']>()
        .mockResolvedValue({ exchange: 'identity.events' }),
      publish: jest.fn((...args: unknown[]) => {
        confirm = args[4] as typeof confirm;
        return false;
      }),
    }) as unknown as ConfirmChannel;
    connection = Object.assign(new EventEmitter(), {
      createConfirmChannel: jest
        .fn<ChannelModel['createConfirmChannel']>()
        .mockResolvedValue(channel),
      close: jest.fn<ChannelModel['close']>().mockImplementation(() => {
        channel.emit('close');
        connection.emit('close');
        return Promise.resolve();
      }),
    }) as unknown as ChannelModel;
    connector = {
      connect: jest.fn<AmqpConnector['connect']>().mockResolvedValue(connection),
    };
    adapter = new RabbitMqRegistrationEventPublisher(
      new ConfigService({
        RABBITMQ_URL: 'amqp://private:password@localhost',
      }),
      connector,
    );
  });

  afterEach(async () => {
    jest.useRealTimers();
    await adapter.onApplicationShutdown();
  });

  async function start(): Promise<{ work: Promise<void> }> {
    const work = adapter.publish(event, '00-11111111111111111111111111111111-2222222222222222-00');
    await new Promise<void>((resolve) => setImmediate(resolve));
    return { work };
  }

  it('waits for confirmation even when publish returns false (buffer flow)', async () => {
    const { work } = await start();
    let settled = false;
    void work.then(() => {
      settled = true;
    });
    expect(settled).toBe(false);
    const args = (channel.publish as unknown as ReturnType<typeof jest.fn>).mock.calls[0];
    expect(args[0]).toBe('identity.events');
    expect(args[1]).toBe('identity.user.registered.v1');
    expect(args[3]).toMatchObject({
      persistent: true,
      mandatory: true,
      messageId: event.eventId,
    });
    confirm(null);
    await expect(work).resolves.toBeUndefined();
  });

  it('rejects basic.return even if the broker subsequently confirms', async () => {
    const { work } = await start();
    channel.emit('return', { properties: { messageId: event.eventId } });
    confirm(null);
    await expect(work).rejects.toMatchObject({
      code: 'REGISTRATION_EVENT_UNROUTABLE',
    });
  });

  it('rejects a nack and reconnects for the next attempt', async () => {
    const { work } = await start();
    confirm(new Error('private-error'));
    await expect(work).rejects.toMatchObject({
      code: 'REGISTRATION_PUBLICATION_NACK',
    });
    const next = await start();
    confirm(null);
    await next.work;
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(connector.connect).toHaveBeenCalledTimes(2);
  });

  it('rejects channel closure before confirmation', async () => {
    const { work } = await start();
    channel.emit('close');
    await expect(work).rejects.toMatchObject({
      code: 'REGISTRATION_CHANNEL_CLOSED',
    });
  });

  it('times out an unconfirmed message without exposing credentials', async () => {
    jest.useFakeTimers();
    const work = adapter.publish(event, 'traceparent');
    const checked = expect(work).rejects.toMatchObject({
      code: 'REGISTRATION_PUBLICATION_TIMEOUT',
    });
    await jest.advanceTimersByTimeAsync(8_001);
    await checked;
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(connection.close).toHaveBeenCalled();
  });
});
