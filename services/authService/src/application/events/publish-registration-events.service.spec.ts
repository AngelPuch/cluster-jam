import { Logger } from '@nestjs/common';
import { afterEach, describe, expect, it, jest } from '@jest/globals';
import type { RegistrationOutboxPort } from '../ports/registration-outbox.port';
import type { RegistrationEventPublisherPort } from '../ports/registration-event-publisher.port';
import { PublishRegistrationEventsService } from './publish-registration-events.service';

const record = {
  id: '11111111-1111-4111-8111-111111111111',
  aggregateId: '22222222-2222-4222-8222-222222222222',
  aggregateVersion: 1,
  occurredAt: new Date('2026-10-20T12:00:00Z'),
  data: {
    userId: '22222222-2222-4222-8222-222222222222',
    initialContactEmail: 'private@example.com',
  },
};

describe('PublishRegistrationEventsService', () => {
  afterEach(() => void jest.restoreAllMocks());

  it('publishes a validated event with a producer trace and safe aggregate logs', async () => {
    const log = jest.spyOn(Logger.prototype, 'log').mockImplementation(() => undefined);
    const publish = jest
      .fn<RegistrationEventPublisherPort['publish']>()
      .mockResolvedValue(undefined);
    const deliverNext = jest
      .fn<RegistrationOutboxPort['deliverNext']>()
      .mockImplementationOnce(async (deliver) => {
        await deliver(record);
        return { status: 'published' };
      })
      .mockResolvedValue({ status: 'empty' });
    const service = new PublishRegistrationEventsService({ deliverNext }, { publish });
    await expect(service.execute()).resolves.toEqual({
      published: 1,
      retried: 0,
    });
    expect(publish.mock.calls[0][0].eventId).toBe(record.id);
    expect(publish.mock.calls[0][1]).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-00$/);
    expect(JSON.stringify(log.mock.calls)).not.toContain('private@example.com');
    expect(deliverNext).toHaveBeenCalledTimes(2);
  });

  it('limits the batch and reports retries without logging raw provider errors', async () => {
    const warn = jest.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);
    const debug = jest.spyOn(Logger.prototype, 'debug').mockImplementation(() => undefined);
    const deliverNext = jest.fn<RegistrationOutboxPort['deliverNext']>().mockResolvedValue({
      status: 'retry',
      code: 'REGISTRATION_BROKER_UNAVAILABLE',
    });
    const publish = jest.fn<RegistrationEventPublisherPort['publish']>();
    await expect(
      new PublishRegistrationEventsService({ deliverNext }, { publish }).execute(2),
    ).resolves.toEqual({ published: 0, retried: 2 });
    expect(deliverNext).toHaveBeenCalledTimes(2);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(debug).toHaveBeenCalledTimes(2);
  });

  it('allows shutdown to stop before the next row', async () => {
    const deliverNext = jest.fn<RegistrationOutboxPort['deliverNext']>();
    const publish = jest.fn<RegistrationEventPublisherPort['publish']>();
    await expect(
      new PublishRegistrationEventsService({ deliverNext }, { publish }).execute(10, () => true),
    ).resolves.toEqual({ published: 0, retried: 0 });
    expect(deliverNext).not.toHaveBeenCalled();
  });

  it('reports a blocked event safely and continues with the next available event', async () => {
    const error = jest.spyOn(Logger.prototype, 'error').mockImplementation(() => undefined);
    jest.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);
    const publish = jest.fn<RegistrationEventPublisherPort['publish']>();
    const deliverNext = jest
      .fn<RegistrationOutboxPort['deliverNext']>()
      .mockResolvedValueOnce({
        status: 'blocked',
        eventId: record.id,
        code: 'REGISTRATION_EVENT_INVALID',
      })
      .mockImplementationOnce(async (deliver) => {
        await deliver(record);
        return { status: 'published' };
      })
      .mockResolvedValue({ status: 'empty' });

    await expect(
      new PublishRegistrationEventsService({ deliverNext }, { publish }).execute(),
    ).resolves.toEqual({ published: 1, retried: 0 });
    expect(publish).toHaveBeenCalledTimes(1);
    expect(deliverNext).toHaveBeenCalledTimes(3);
    expect(error).toHaveBeenCalledWith({
      event: 'auth.outbox.event.blocked',
      event_id: record.id,
      code: 'REGISTRATION_EVENT_INVALID',
    });
    expect(JSON.stringify(error.mock.calls)).not.toContain('private@example.com');
  });
});
