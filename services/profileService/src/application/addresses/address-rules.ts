import { isISO31661Alpha2 } from 'class-validator';
import type { AddressFields, CreateAddressInput, UpdateAddressInput } from './address';
import { AddressError, AddressFailure } from './address.error';

export const ADDRESS_TEXT_LIMITS = {
    label: 40,
    recipient: 120,
    street: 160,
    exteriorNumber: 20,
    interiorNumber: 20,
    neighborhood: 120,
    municipality: 120,
    state: 120,
    postalCode: 5,
    country: 2,
} as const;
const required = [
    'label',
    'recipient',
    'street',
    'exteriorNumber',
    'neighborhood',
    'municipality',
    'state',
    'postalCode',
    'country',
] as const;

function invalid(): never {
    throw new AddressError(AddressFailure.InvalidInput);
}

function normalize(input: CreateAddressInput | UpdateAddressInput, creating: boolean): UpdateAddressInput {
    if (typeof input !== 'object' || input === null || Array.isArray(input)) invalid();
    if (Object.keys(input).some((key) => key !== 'isDefault' && !Object.hasOwn(ADDRESS_TEXT_LIMITS, key))) invalid();
    const result: { -readonly [K in keyof AddressFields]?: AddressFields[K] } = {};
    for (const key of Object.keys(ADDRESS_TEXT_LIMITS) as Array<keyof typeof ADDRESS_TEXT_LIMITS>) {
        const value = input[key];
        if (value === undefined) continue;
        if (key === 'interiorNumber' && value === null) {
            result.interiorNumber = null;
            continue;
        }
        if (typeof value !== 'string') invalid();
        const text = value.trim();
        if (!text || Array.from(text).length > ADDRESS_TEXT_LIMITS[key] || /\p{Cc}/u.test(text)) invalid();
        result[key] = key === 'country' ? text.toUpperCase() : text;
    }
    if (input.isDefault !== undefined) {
        if (typeof input.isDefault !== 'boolean') invalid();
        result.isDefault = input.isDefault;
    }
    if (result.country !== undefined && !isISO31661Alpha2(result.country)) invalid();
    if (Object.keys(result).length === 0 || (creating && required.some((key) => result[key] === undefined))) invalid();
    return result;
}

export function normalizeCreateAddress(input: CreateAddressInput): AddressFields {
    const result = normalize(input, true);
    return {
        ...result,
        interiorNumber: result.interiorNumber ?? null,
        isDefault: result.isDefault ?? false,
    } as AddressFields;
}
export function normalizeUpdateAddress(input: UpdateAddressInput): UpdateAddressInput {
    return normalize(input, false);
}
