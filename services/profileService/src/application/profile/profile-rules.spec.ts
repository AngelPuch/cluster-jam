import { completeProfile, normalizeProfileUpdate } from './profile-rules';
import { ProfileError, ProfileFailure } from './profile.error';
import type { CustomerProfile, UpdateProfileInput } from './profile';

const pending: CustomerProfile = {
    userId: '11111111-1111-4111-8111-111111111111',
    fullName: null,
    phone: null,
    contactEmail: 'initial@example.com',
    onboardingStatus: 'PENDING',
    createdAt: new Date(),
    updatedAt: new Date(),
    revision: 'a'.repeat(64),
};

describe('Profile update and onboarding rules', () => {
    it('trims allowed fields without changing email case or inventing omitted values', () => {
        expect(
            normalizeProfileUpdate({
                fullName: '  María López  ',
                phone: ' +52 (55) 1234-5678 ',
                contactEmail: ' Contact@example.com ',
            }),
        ).toEqual({ fullName: 'María López', phone: '+52 (55) 1234-5678', contactEmail: 'Contact@example.com' });
        expect(normalizeProfileUpdate({ fullName: 'María' })).toEqual({ fullName: 'María' });
    });

    it.each([
        null,
        [],
        {},
        { fullName: undefined },
        { fullName: null },
        { fullName: '' },
        { fullName: '   ' },
        { fullName: 123 },
        { fullName: 'x'.repeat(121) },
        { fullName: 'María\nLópez' },
        { phone: '123456' },
        { phone: '1'.repeat(16) },
        { phone: '1'.repeat(31) },
        { phone: '+52 CALL NOW' },
        { phone: '++525512345678' },
        { phone: null },
        { contactEmail: '' },
        { contactEmail: 'invalid' },
        { contactEmail: 'a'.repeat(250) + '@example.com' },
        { contactEmail: null },
        { userId: pending.userId },
        { onboardingStatus: 'COMPLETED' },
        { fullName: 'María', role: 'administrador' },
    ])('rejects malformed, blank, oversized and privileged input %#', (input) => {
        expect(() => normalizeProfileUpdate(input as UpdateProfileInput)).toThrow(
            new ProfileError(ProfileFailure.InvalidUpdate),
        );
    });

    it('preserves omitted values and stays pending until both name and phone are valid', () => {
        expect(completeProfile(pending, { fullName: 'María' })).toEqual({
            fullName: 'María',
            phone: null,
            contactEmail: 'initial@example.com',
            onboardingStatus: 'PENDING',
        });
        expect(completeProfile(pending, { phone: '5551234567' }).onboardingStatus).toBe('PENDING');
        expect(completeProfile(pending, { fullName: 'María', phone: '5551234567' }).onboardingStatus).toBe('COMPLETED');
    });

    it('changes contact email independently and does not require an address to complete', () => {
        expect(
            completeProfile(pending, { fullName: 'María', phone: '5551234567', contactEmail: 'new@example.com' }),
        ).toEqual({
            fullName: 'María',
            phone: '5551234567',
            contactEmail: 'new@example.com',
            onboardingStatus: 'COMPLETED',
        });
        expect(pending.fullName).toBeNull();
    });

    it('requires an explicit genuine contact email when repairing legacy data', () => {
        const legacy = { ...pending, contactEmail: null };
        expect(() => completeProfile(legacy, { fullName: 'María' })).toThrow(
            new ProfileError(ProfileFailure.ContactEmailRequired),
        );
        expect(completeProfile(legacy, { contactEmail: 'real@example.com' }).contactEmail).toBe('real@example.com');
    });

    it('does not promote legacy profiles containing an invalid phone', () => {
        expect(
            completeProfile(
                { ...pending, fullName: 'María', phone: 'old-invalid-phone' },
                { contactEmail: 'new@example.com' },
            ).onboardingStatus,
        ).toBe('PENDING');
    });
});
