import type { MigrationInterface, QueryRunner } from 'typeorm';

export const PAYMENTS_SCHEMA_VERSION = 1795737600000;
export const PAYMENTS_MIGRATION_NAME = 'CreatePayments1795737600000';

export class CreatePayments1795737600000 implements MigrationInterface {
    name = PAYMENTS_MIGRATION_NAME;

    async up(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`
            CREATE TABLE app.pago (
                id uuid PRIMARY KEY,
                pedido_id uuid NOT NULL UNIQUE,
                comprador_id uuid NOT NULL,
                reserva_id uuid NOT NULL,
                reserva_expira_en timestamptz NOT NULL,
                importe_centavos bigint NOT NULL CHECK (importe_centavos BETWEEN 1 AND 9007199254740991),
                moneda varchar(3) NOT NULL CHECK (moneda = 'MXN'),
                estado varchar(20) NOT NULL DEFAULT 'PENDIENTE'
                    CHECK (estado IN ('PENDIENTE', 'PAGADO', 'CANCELADO', 'REEMBOLSADO', 'FALLIDO')),
                stripe_payment_intent_id varchar(255) UNIQUE,
                estado_proveedor varchar(64),
                creado_en timestamptz NOT NULL DEFAULT now(),
                actualizado_en timestamptz NOT NULL DEFAULT now(),
                UNIQUE (id, importe_centavos, moneda),
                CHECK (estado NOT IN ('PAGADO', 'REEMBOLSADO') OR stripe_payment_intent_id IS NOT NULL)
            );
            CREATE TABLE app.reembolso (
                id uuid PRIMARY KEY,
                pago_id uuid NOT NULL UNIQUE,
                importe_centavos bigint NOT NULL CHECK (importe_centavos BETWEEN 1 AND 9007199254740991),
                moneda varchar(3) NOT NULL CHECK (moneda = 'MXN'),
                motivo varchar(200) NOT NULL CHECK (btrim(motivo) <> ''),
                stripe_refund_id varchar(255) UNIQUE,
                estado_proveedor varchar(64),
                creado_en timestamptz NOT NULL DEFAULT now(),
                actualizado_en timestamptz NOT NULL DEFAULT now(),
                FOREIGN KEY (pago_id, importe_centavos, moneda) REFERENCES app.pago(id, importe_centavos, moneda)
            );
            CREATE TABLE app.inbox_pagos (
                consumidor varchar(160) NOT NULL CHECK (btrim(consumidor) <> ''),
                message_id varchar(255) NOT NULL CHECK (btrim(message_id) <> ''),
                procesado_en timestamptz NOT NULL DEFAULT now(),
                PRIMARY KEY (consumidor, message_id)
            );
            CREATE TABLE app.outbox_pagos (
                id uuid PRIMARY KEY,
                exchange varchar(80) NOT NULL CHECK (exchange = 'payments.events'),
                routing_key varchar(160) NOT NULL CHECK (btrim(routing_key) <> ''),
                cuerpo jsonb NOT NULL CHECK (jsonb_typeof(cuerpo) = 'object'),
                estado varchar(12) NOT NULL DEFAULT 'PENDING' CHECK (estado IN ('PENDING', 'PUBLISHED')),
                creado_en timestamptz NOT NULL DEFAULT now(),
                publicado_en timestamptz,
                CHECK ((estado = 'PENDING' AND publicado_en IS NULL) OR
                       (estado = 'PUBLISHED' AND publicado_en IS NOT NULL))
            );
            CREATE INDEX outbox_pagos_pending ON app.outbox_pagos(creado_en, id) WHERE estado = 'PENDING';
            GRANT SELECT, INSERT, UPDATE ON app.pago, app.reembolso, app.outbox_pagos TO app_pagos;
            GRANT SELECT, INSERT ON app.inbox_pagos TO app_pagos;
            GRANT SELECT ON app.migrations_pagos TO app_pagos;
        `);
    }

    async down(queryRunner: QueryRunner): Promise<void> {
        await queryRunner.query(`
            DROP TABLE app.outbox_pagos;
            DROP TABLE app.inbox_pagos;
            DROP TABLE app.reembolso;
            DROP TABLE app.pago;
        `);
    }
}
