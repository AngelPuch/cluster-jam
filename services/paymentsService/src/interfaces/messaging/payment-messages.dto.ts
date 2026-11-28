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

import { PaymentMessageType, type PaymentCommand } from '../../application/payments/payment-messages';
export { PaymentMessageType } from '../../application/payments/payment-messages';
export type { PaymentCommand, PaymentEvent } from '../../application/payments/payment-messages';

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
