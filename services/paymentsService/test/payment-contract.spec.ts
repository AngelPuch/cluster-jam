import 'reflect-metadata';
import { randomUUID } from 'node:crypto';
import {
    InvalidPaymentCommand,
    parsePaymentCommand,
    PaymentMessageType,
} from '../src/interfaces/messaging/payment-messages.dto';

function command() {
    return {
        messageId: randomUUID(),
        type: PaymentMessageType.Enable,
        orderId: randomUUID(),
        occurredAt: '2026-11-27T18:00:00Z',
        data: {
            reservationId: randomUUID(),
            reservationExpiresAt: '2026-11-27T18:15:00+00:00',
            buyerId: randomUUID(),
            amountCents: 19900,
            currency: 'MXN',
        },
    };
}

describe('Payments saga command contract', () => {
    it('accepts the agreed enable/cancel/refund shapes without canonical timestamps', () => {
        const input = command();
        expect(parsePaymentCommand(input)).toEqual(input);
        for (const type of [PaymentMessageType.Cancel, PaymentMessageType.Refund]) {
            const action = { ...input, type, data: { paymentId: randomUUID(), reason: ' Customer cancellation ' } };
            expect(parsePaymentCommand(action).data).toEqual({ ...action.data, reason: 'Customer cancellation' });
        }
    });

    it('rejects invalid money, currency and fields that could override financial state', () => {
        const input = command();
        for (const amountCents of [0, -1, 1.5, '19900', Number.MAX_SAFE_INTEGER + 1]) {
            expect(() => parsePaymentCommand({ ...input, data: { ...input.data, amountCents } })).toThrow(
                InvalidPaymentCommand,
            );
        }
        expect(() => parsePaymentCommand({ ...input, data: { ...input.data, currency: 'USD' } })).toThrow(
            InvalidPaymentCommand,
        );
        expect(() => parsePaymentCommand({ ...input, data: { ...input.data, status: 'PAGADO' } })).toThrow(
            InvalidPaymentCommand,
        );
    });
});
