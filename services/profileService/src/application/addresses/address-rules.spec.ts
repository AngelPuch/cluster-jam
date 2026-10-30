import { normalizeCreateAddress, normalizeUpdateAddress, ADDRESS_TEXT_LIMITS } from './address-rules';
import type { CreateAddressInput, UpdateAddressInput } from './address';
import { AddressError, AddressFailure } from './address.error';

const valid: CreateAddressInput = {
    label: 'Casa',
    recipient: 'María López',
    street: 'Reforma',
    exteriorNumber: '123',
    neighborhood: 'Centro',
    municipality: 'Cuauhtémoc',
    state: 'CDMX',
    postalCode: '06000',
    country: 'MX',
};

describe('Address input rules', () => {
    it('normalizes text/country, preserves postal zeroes and leaves the default unselected', () => {
        expect(normalizeCreateAddress({ ...valid, label: ' Casa ', country: ' mx ' })).toEqual({
            ...valid,
            interiorNumber: null,
            isDefault: false,
        });
        expect(normalizeCreateAddress({ ...valid, isDefault: true, interiorNumber: ' 4B ' })).toMatchObject({
            isDefault: true,
            interiorNumber: '4B',
        });
    });
    it('preserves omitted fields and permits null only to clear the interior number', () => {
        expect(normalizeUpdateAddress({ label: ' Oficina ' })).toEqual({ label: 'Oficina' });
        expect(normalizeUpdateAddress({ interiorNumber: null, isDefault: false })).toEqual({
            interiorNumber: null,
            isDefault: false,
        });
    });
    it.each(Object.keys(ADDRESS_TEXT_LIMITS))('enforces the schema text limit for %s', (key) => {
        const limit = ADDRESS_TEXT_LIMITS[key as keyof typeof ADDRESS_TEXT_LIMITS];
        expect(() => normalizeUpdateAddress({ [key]: 'x'.repeat(limit + 1) })).toThrow(
            new AddressError(AddressFailure.InvalidInput),
        );
    });
    it.each([
        'label',
        'recipient',
        'street',
        'exteriorNumber',
        'neighborhood',
        'municipality',
        'state',
        'postalCode',
        'country',
    ])('requires %s on create and rejects null/blank replacements', (key) => {
        const missing = { ...valid } as Record<string, unknown>;
        delete missing[key];
        expect(() => normalizeCreateAddress(missing as unknown as CreateAddressInput)).toThrow(AddressError);
        for (const value of [null, '', '  '])
            expect(() => normalizeUpdateAddress({ [key]: value })).toThrow(AddressError);
    });
    it.each([
        null,
        [],
        {},
        { label: undefined },
        { label: 123 },
        { street: 'Line\nBreak' },
        { country: 'ZZ' },
        { country: 'MEX' },
        { country: 52 },
        { isDefault: null },
        { isDefault: 'false' },
        { interiorNumber: '' },
        { interiorNumber: 4 },
        { userId: 'someone' },
        { id: 'caller-id' },
        { revision: 'forged' },
        { label: 'Casa', onboardingStatus: 'COMPLETED' },
    ])('rejects malformed or privileged updates %#', (input) => {
        expect(() => normalizeUpdateAddress(input as UpdateAddressInput)).toThrow(
            new AddressError(AddressFailure.InvalidInput),
        );
    });
});
