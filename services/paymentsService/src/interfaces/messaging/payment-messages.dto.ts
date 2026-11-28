import { plainToInstance, Transform, type ClassConstructor } from 'class-transformer';
import {
    Equals,
    IsIn,
    IsInt,
    IsISO8601,
    IsNotEmpty,
    IsObject,
    IsString,
    IsUUID,
    Max,
    MaxLength,
    Min,
    validateSync,
} from 'class-validator';

export enum PaymentMessageType {
    Enable = 'cmd.payments.enable-payment.v1',
    Cancel = 'cmd.payments.cancel-payment.v1',
    Refund = 'cmd.payments.refund-full.v1',
    Enabled = 'payments.payment.enabled.v1',
    Succeeded = 'payments.payment.succeeded.v1',
    NotCompleted = 'payments.payment.not-completed.v1',
    RefundSucceeded = 'payments.refund.succeeded.v1',
}

class MoneyDto {
    @IsInt() @Min(1) @Max(Number.MAX_SAFE_INTEGER) amountCents!: number;
    @Equals('MXN') currency!: 'MXN';
}

export class EnablePaymentData extends MoneyDto {
    @IsUUID() reservationId!: string;
    @IsISO8601({ strict: true, strictSeparator: true }) reservationExpiresAt!: string;
    @IsUUID() buyerId!: string;
}

export class PaymentActionData {
    @IsUUID() paymentId!: string;
    @Transform(({ value }: { value: unknown }) => (typeof value === 'string' ? value.trim() : value))
    @IsString()
    @IsNotEmpty()
    @MaxLength(200)
    reason!: string;
}

interface PaymentEnvelope<T extends PaymentMessageType, D> {
    messageId: string;
    type: T;
    orderId: string;
    occurredAt: string;
    data: D;
}

export type PaymentCommand =
    | PaymentEnvelope<PaymentMessageType.Enable, EnablePaymentData>
    | PaymentEnvelope<PaymentMessageType.Cancel, PaymentActionData>
    | PaymentEnvelope<PaymentMessageType.Refund, PaymentActionData>;

export type PaymentEvent =
    | PaymentEnvelope<PaymentMessageType.Enabled, { paymentId: string; reservationId: string }>
    | PaymentEnvelope<
          PaymentMessageType.Succeeded,
          { paymentId: string; reservationId: string; amountCents: number; currency: 'MXN' }
      >
    | PaymentEnvelope<
          PaymentMessageType.NotCompleted,
          { paymentId: string; status: 'CANCELADO' | 'FALLIDO'; reason: string }
      >
    | PaymentEnvelope<PaymentMessageType.RefundSucceeded, { paymentId: string; amountCents: number; currency: 'MXN' }>;

class CommandEnvelopeDto {
    @IsUUID() messageId!: string;
    @IsIn([PaymentMessageType.Enable, PaymentMessageType.Cancel, PaymentMessageType.Refund])
    type!: PaymentCommand['type'];
    @IsUUID() orderId!: string;
    @IsISO8601({ strict: true, strictSeparator: true }) occurredAt!: string;
    @IsObject() data!: object;
}

export class InvalidPaymentCommand extends Error {
    constructor() {
        super('PAYMENT_COMMAND_INVALID');
    }
}

const OPTIONS = {
    whitelist: true,
    forbidNonWhitelisted: true,
    forbidUnknownValues: true,
    validationError: { target: false, value: false },
};
const DATA_TYPES: Record<PaymentCommand['type'], ClassConstructor<object>> = {
    [PaymentMessageType.Enable]: EnablePaymentData,
    [PaymentMessageType.Cancel]: PaymentActionData,
    [PaymentMessageType.Refund]: PaymentActionData,
};

export function parsePaymentCommand(input: unknown): PaymentCommand {
    if (typeof input !== 'object' || input === null || Array.isArray(input)) throw new InvalidPaymentCommand();
    const envelope = plainToInstance(CommandEnvelopeDto, input);
    if (validateSync(envelope, OPTIONS).length > 0) throw new InvalidPaymentCommand();
    const data = plainToInstance(DATA_TYPES[envelope.type], envelope.data);
    if (validateSync(data, OPTIONS).length > 0) throw new InvalidPaymentCommand();
    return { ...envelope, data } as PaymentCommand;
}
