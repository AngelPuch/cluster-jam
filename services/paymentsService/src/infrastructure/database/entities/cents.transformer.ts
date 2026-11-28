import type { ValueTransformer } from 'typeorm';
import { requirePositiveCents } from '../../../application/payments/payment';

export const centsTransformer: ValueTransformer = {
    to: (value: unknown): number => requirePositiveCents(value),
    from: (value: unknown): number => requirePositiveCents(typeof value === 'string' ? Number(value) : value),
};
