import { Column, CreateDateColumn, Entity, PrimaryColumn } from 'typeorm';

@Entity({ schema: 'app', name: 'outbox_pagos' })
export class OutboxEntity {
    @PrimaryColumn({ type: 'uuid' }) id!: string;
    @Column({ type: 'varchar', length: 80 }) exchange!: string;
    @Column({ name: 'routing_key', type: 'varchar', length: 160 }) routingKey!: string;
    @Column({ name: 'cuerpo', type: 'jsonb' }) body!: Record<string, unknown>;
    @Column({ name: 'estado', type: 'varchar', length: 12, default: 'PENDING' }) status!: 'PENDING' | 'PUBLISHED';
    @CreateDateColumn({ name: 'creado_en', type: 'timestamptz' }) createdAt!: Date;
    @Column({ name: 'publicado_en', type: 'timestamptz', nullable: true }) publishedAt!: Date | null;
}
