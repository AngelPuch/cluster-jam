import { Inject, Injectable, OnApplicationShutdown } from '@nestjs/common';
import type { Pool, PoolClient } from 'pg';

import {
    REGISTRATION_ROUTING_KEY,
    RegistrationPublicationError,
    type RegistrationOutboxRecord,
} from '../../application/events/registration-event';
import type {
    OutboxDeliveryResult,
    RegistrationOutboxPort,
} from '../../application/ports/registration-outbox.port';
import { OUTBOX_DATABASE } from './outbox-database.provider';

@Injectable()
export class PostgresRegistrationOutboxAdapter
    implements RegistrationOutboxPort, OnApplicationShutdown
{
    constructor(@Inject(OUTBOX_DATABASE) private readonly pool: Pool | null) {}

    async deliverNext(
        deliver: (record: RegistrationOutboxRecord) => Promise<void>,
    ): Promise<OutboxDeliveryResult> {
        if (!this.pool) throw new Error('Outbox publisher is disabled.');
        const client = await this.pool.connect();
        let destroyClient = false;
        const onClientError = (): void => {
            destroyClient = true;
        };
        client.on('error', onClientError);
        try {
            await client.query('BEGIN');
            const result = await client.query<RegistrationOutboxRecord>(
                `SELECT id, agregado_id AS "aggregateId",
                        version_agregado AS "aggregateVersion",
                        ocurrido_en AS "occurredAt", datos AS data
                 FROM integration.auth_outbox
                 WHERE publicado_en IS NULL AND tipo = $1
                   AND COALESCE(proximo_intento_en, ocurrido_en) <= now()
                 ORDER BY COALESCE(proximo_intento_en, ocurrido_en), ocurrido_en, id
                 LIMIT 1 FOR UPDATE SKIP LOCKED`,
                [REGISTRATION_ROUTING_KEY],
            );
            const row = result.rows[0];
            if (!row) {
                await client.query('COMMIT');
                return { status: 'empty' };
            }

            let delivery: OutboxDeliveryResult;
            try {
                await deliver(row);
                delivery = { status: 'published' };
            } catch (error) {
                delivery = {
                    status: 'retry',
                    code:
                        error instanceof RegistrationPublicationError
                            ? error.code
                            : 'REGISTRATION_PUBLICATION_FAILED',
                };
            }

            if (delivery.status === 'published') {
                await client.query(
                    `UPDATE integration.auth_outbox
                     SET publicado_en = clock_timestamp(),
                         intentos = LEAST(intentos::bigint + 1, 2147483647)::integer,
                         proximo_intento_en = NULL
                     WHERE id = $1 AND publicado_en IS NULL`,
                    [row.id],
                );
            } else {
                await this.scheduleRetry(client, row.id);
            }
            await client.query('COMMIT');
            return delivery;
        } catch {
            destroyClient = true;
            try {
                await client.query('ROLLBACK');
            } catch {
                /* Discard client. */
            }
            throw new Error('Registration outbox transaction failed.');
        } finally {
            client.off('error', onClientError);
            client.release(destroyClient);
        }
    }

    private async scheduleRetry(
        client: PoolClient,
        eventId: string,
    ): Promise<void> {
        await client.query(
            `UPDATE integration.auth_outbox
             SET intentos = LEAST(intentos::bigint + 1, 2147483647)::integer,
                 proximo_intento_en = clock_timestamp()
                     + make_interval(secs => LEAST(60, 2 * power(2, LEAST(intentos, 5)))::integer)
             WHERE id = $1 AND publicado_en IS NULL`,
            [eventId],
        );
    }

    async onApplicationShutdown(): Promise<void> {
        await this.pool?.end();
    }
}
