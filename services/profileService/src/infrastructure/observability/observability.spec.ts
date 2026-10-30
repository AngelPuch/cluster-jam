import { jest } from '@jest/globals';
import { randomUUID } from 'node:crypto';
import { JsonLogger } from './json-logger.service';
import { TraceContextService } from './trace-context.service';

describe('Messaging trace correlation and privacy', () => {
    const originalLevel = process.env.LOG_LEVEL;
    const records: string[] = [];
    beforeEach(() => {
        records.length = 0;
        process.env.LOG_LEVEL = 'DEBUG';
        jest.spyOn(process.stdout, 'write').mockImplementation((chunk) => {
            records.push(String(chunk));
            return true;
        });
        jest.spyOn(process.stderr, 'write').mockImplementation((chunk) => {
            records.push(String(chunk));
            return true;
        });
    });
    afterEach(() => {
        if (originalLevel === undefined) delete process.env.LOG_LEVEL;
        else process.env.LOG_LEVEL = originalLevel;
        jest.restoreAllMocks();
    });

    it('propagates a W3C parent to a new consumer span and structured log', async () => {
        const tracing = new TraceContextService();
        const logger = new JsonLogger();
        const eventId = randomUUID();
        await tracing.runConsumer('00-11111111111111111111111111111111-2222222222222222-01', async () => {
            await Promise.resolve();
            logger.log({ event: 'profile.broker.connected', event_id: eventId });
        });
        const record: unknown = JSON.parse(records[0]);
        expect(record).toMatchObject({
            service_name: 'profile-service',
            level: 'INFO',
            event_id: eventId,
            trace_id: '11111111111111111111111111111111',
            span_id: expect.stringMatching(/^[0-9a-f]{16}$/) as string,
        });
        expect((record as { span_id: string }).span_id).not.toBe('2222222222222222');
    });

    it('logs only allowlisted metadata, excluding emails, payloads and raw errors', () => {
        const logger = new JsonLogger();
        logger.warn({
            event: 'profile.event.dead-lettered',
            code: 'REGISTRATION_EVENT_INVALID',
            event_id: 'private@example.com',
            body: { initialContactEmail: 'private@example.com' },
            password: 'private-password',
            authorization: 'Bearer private-token',
            stack: 'private-stack',
        });
        logger.error(new Error('private@example.com private-password private-token'));
        const output = records.join('');
        for (const privateValue of ['private@example.com', 'private-password', 'private-token', 'private-stack']) {
            expect(output).not.toContain(privateValue);
        }
        expect(JSON.parse(records[0]) as unknown).toMatchObject({ code: 'REGISTRATION_EVENT_INVALID' });
    });

    it('keeps HTTP trace correlation for completion callbacks invoked outside request context', () => {
        const tracing = new TraceContextService();
        const logger = new JsonLogger();
        let complete = () => {};
        tracing.runHttp('00-11111111111111111111111111111111-2222222222222222-01', () => {
            expect(tracing.traceId).toBe('11111111111111111111111111111111');
            complete = tracing.bindHttp(() => {
                logger.log({
                    event: 'http.request.completed',
                    http_status: 422,
                    duration_ms: 25,
                    url: '/profiles/private@example.com?token=private-token',
                    phone: 'private-phone',
                    authorization: 'Bearer private-token',
                    body: { fullName: 'Private Customer' },
                });
                tracing.endHttp(422);
            });
        });
        complete();
        expect(JSON.parse(records[0]) as unknown).toMatchObject({
            trace_id: '11111111111111111111111111111111',
            event: 'http.request.completed',
            http_status: 422,
            duration_ms: 25,
        });
        expect(records.join('')).not.toMatch(/private@example|private-token|private-phone|Private Customer/);
    });
});
