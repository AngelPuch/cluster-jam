import { CreateDateColumn, Entity, PrimaryColumn } from 'typeorm';

@Entity({ schema: 'app', name: 'inbox_pagos' })
export class InboxEntity {
    @PrimaryColumn({ name: 'consumidor', type: 'varchar', length: 160 }) consumer!: string;
    // AMQP uses UUIDs; a separate webhook consumer can store Stripe evt_* IDs.
    @PrimaryColumn({ name: 'message_id', type: 'varchar', length: 255 }) messageId!: string;
    @CreateDateColumn({ name: 'procesado_en', type: 'timestamptz' }) processedAt!: Date;
}
