import { beforeEach, describe, expect, it, jest } from '@jest/globals';
import type { Pool, PoolClient } from 'pg';
import { RegistrationPublicationError } from '../../application/events/registration-event';
import { PostgresRegistrationOutboxAdapter } from './postgres-registration-outbox.adapter';

const row = {
    id: 'event-id',
    aggregateId: 'user-id',
    aggregateVersion: 1,
    occurredAt: new Date(),
    data: {},
};

describe('PostgresRegistrationOutboxAdapter', () => {
    let queries: { sql: string; values?: unknown[] }[];
    let client: PoolClient;
    let adapter: PostgresRegistrationOutboxAdapter;
    let selected: (typeof row)[];
    let failCommit: boolean;
    let release: ReturnType<typeof jest.fn>;

    beforeEach(() => {
        queries = [];
        selected = [row];
        failCommit = false;
        release = jest.fn();
        client = {
            query: jest.fn((sql: string, values?: unknown[]) => {
                queries.push({ sql, values });
                if (sql === 'COMMIT' && failCommit)
                    throw new Error('private-database-url');
                return Promise.resolve({
                    rows: sql.startsWith('SELECT') ? selected : [],
                    rowCount: 1,
                });
            }),
            release,
            on: jest.fn(),
            off: jest.fn(),
        } as unknown as PoolClient;
        const pool = {
            connect: jest
                .fn<() => Promise<PoolClient>>()
                .mockResolvedValue(client),
        } as unknown as Pool;
        adapter = new PostgresRegistrationOutboxAdapter(pool);
    });

    it('holds a row lock and waits for delivery before setting publicado_en', async () => {
        let confirm!: () => void;
        const confirmation = new Promise<void>((resolve) => {
            confirm = resolve;
        });
        const deliver = jest.fn(() => confirmation);
        const result = adapter.deliverNext(deliver);
        await new Promise<void>((resolve) => setImmediate(resolve));
        expect(queries.find((q) => q.sql.startsWith('SELECT'))?.sql).toContain(
            'FOR UPDATE SKIP LOCKED',
        );
        expect(queries.some((q) => q.sql.startsWith('UPDATE'))).toBe(false);
        confirm();
        await expect(result).resolves.toEqual({ status: 'published' });
        const update = queries.find((q) => q.sql.startsWith('UPDATE'));
        expect(update?.sql).toContain('publicado_en = clock_timestamp()');
        expect(update?.values).toEqual([row.id]);
        expect(queries.at(-1)?.sql).toBe('COMMIT');
        expect(release).toHaveBeenCalledWith(false);
    });

    it('persists retry state after a nack without marking publication', async () => {
        const deliver = jest
            .fn<() => Promise<void>>()
            .mockRejectedValue(
                new RegistrationPublicationError(
                    'REGISTRATION_PUBLICATION_NACK',
                ),
            );
        await expect(adapter.deliverNext(deliver)).resolves.toEqual({
            status: 'retry',
            code: 'REGISTRATION_PUBLICATION_NACK',
        });
        const update = queries.find((q) => q.sql.startsWith('UPDATE'));
        expect(update?.sql).toContain('proximo_intento_en = clock_timestamp()');
        expect(update?.sql).not.toContain('publicado_en =');
        expect(queries.at(-1)?.sql).toBe('COMMIT');
    });

    it('rolls back and discards a connection when the post-confirm commit fails', async () => {
        failCommit = true;
        await expect(
            adapter.deliverNext(() => Promise.resolve()),
        ).rejects.toThrow('Registration outbox transaction failed.');
        expect(queries.at(-1)?.sql).toBe('ROLLBACK');
        expect(release).toHaveBeenCalledWith(true);
    });

    it('commits an empty poll without invoking delivery', async () => {
        selected = [];
        const deliver = jest.fn<() => Promise<void>>();
        await expect(adapter.deliverNext(deliver)).resolves.toEqual({
            status: 'empty',
        });
        expect(deliver).not.toHaveBeenCalled();
        expect(queries.some((q) => q.sql.startsWith('UPDATE'))).toBe(false);
    });
});
