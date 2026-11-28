import { Column, CreateDateColumn, Entity, PrimaryColumn, UpdateDateColumn } from 'typeorm';
import { centsTransformer } from './cents.transformer';

@Entity({ schema: 'app', name: 'reembolso' })
export class RefundEntity {
    @PrimaryColumn({ type: 'uuid' }) id!: string;
    @Column({ name: 'pago_id', type: 'uuid', unique: true }) paymentId!: string;
    @Column({ name: 'importe_centavos', type: 'bigint', transformer: centsTransformer }) amountCents!: number;
    @Column({ name: 'moneda', type: 'varchar', length: 3 }) currency!: 'MXN';
    @Column({ name: 'motivo', type: 'varchar', length: 200 }) reason!: string;
    @Column({ name: 'stripe_refund_id', type: 'varchar', length: 255, nullable: true, unique: true })
    stripeRefundId!: string | null;
    @Column({ name: 'stripe_creacion_iniciada_en', type: 'timestamptz', nullable: true })
    stripeCreationStartedAt!: Date | null;
    @Column({ name: 'estado_proveedor', type: 'varchar', length: 64, nullable: true }) providerStatus!: string | null;
    @CreateDateColumn({ name: 'creado_en', type: 'timestamptz' }) createdAt!: Date;
    @UpdateDateColumn({ name: 'actualizado_en', type: 'timestamptz' }) updatedAt!: Date;
}
