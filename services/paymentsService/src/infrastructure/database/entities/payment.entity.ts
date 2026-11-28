import { Column, CreateDateColumn, Entity, PrimaryColumn, UpdateDateColumn } from 'typeorm';
import { PaymentStatus } from '../../../application/payments/payment';
import { centsTransformer } from './cents.transformer';

@Entity({ schema: 'app', name: 'pago' })
export class PaymentEntity {
    @PrimaryColumn({ type: 'uuid' }) id!: string;
    @Column({ name: 'pedido_id', type: 'uuid', unique: true }) orderId!: string;
    @Column({ name: 'comprador_id', type: 'uuid' }) buyerId!: string;
    @Column({ name: 'reserva_id', type: 'uuid' }) reservationId!: string;
    @Column({ name: 'reserva_expira_en', type: 'timestamptz' }) reservationExpiresAt!: Date;
    @Column({ name: 'importe_centavos', type: 'bigint', transformer: centsTransformer }) amountCents!: number;
    @Column({ name: 'moneda', type: 'varchar', length: 3 }) currency!: 'MXN';
    @Column({ name: 'estado', type: 'varchar', length: 20, default: PaymentStatus.Pending }) status!: PaymentStatus;
    @Column({ name: 'stripe_payment_intent_id', type: 'varchar', length: 255, nullable: true, unique: true })
    stripePaymentIntentId!: string | null;
    @Column({ name: 'stripe_creacion_iniciada_en', type: 'timestamptz', nullable: true })
    stripeCreationStartedAt!: Date | null;
    @Column({ name: 'estado_proveedor', type: 'varchar', length: 64, nullable: true }) providerStatus!: string | null;
    @CreateDateColumn({ name: 'creado_en', type: 'timestamptz' }) createdAt!: Date;
    @UpdateDateColumn({ name: 'actualizado_en', type: 'timestamptz' }) updatedAt!: Date;
}
