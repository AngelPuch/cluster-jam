import { isEmail } from 'class-validator';
import type { CustomerProfile, ProfileChanges, UpdateProfileInput } from './profile';
import { ProfileError, ProfileFailure } from './profile.error';

export const PROFILE_LIMITS = { fullName: 120, phone: 30, contactEmail: 254 } as const;

export function isValidPhone(value: string): boolean {
    const digits = value.replace(/\D/g, '').length;
    return value.length <= PROFILE_LIMITS.phone && /^\+?[0-9 ().-]+$/.test(value) && digits >= 7 && digits <= 15;
}

function text(value: unknown, max: number): string {
    if (typeof value !== 'string') throw new ProfileError(ProfileFailure.InvalidUpdate);
    const trimmed = value.trim();
    if (!trimmed || Array.from(trimmed).length > max || /\p{Cc}/u.test(trimmed)) {
        throw new ProfileError(ProfileFailure.InvalidUpdate);
    }
    return trimmed;
}

export function normalizeProfileUpdate(input: UpdateProfileInput): UpdateProfileInput {
    if (typeof input !== 'object' || input === null || Array.isArray(input)) {
        throw new ProfileError(ProfileFailure.InvalidUpdate);
    }
    const keys = Object.keys(input);
    if (keys.length === 0 || keys.some((key) => !Object.hasOwn(PROFILE_LIMITS, key))) {
        throw new ProfileError(ProfileFailure.InvalidUpdate);
    }
    const update: { fullName?: string; phone?: string; contactEmail?: string } = {};
    for (const key of ['fullName', 'phone', 'contactEmail'] as const) {
        if (input[key] !== undefined) update[key] = text(input[key], PROFILE_LIMITS[key]);
    }
    if (
        Object.keys(update).length === 0 ||
        (update.phone !== undefined && !isValidPhone(update.phone)) ||
        (update.contactEmail !== undefined && !isEmail(update.contactEmail))
    ) {
        throw new ProfileError(ProfileFailure.InvalidUpdate);
    }
    return update;
}

export function completeProfile(current: CustomerProfile, update: UpdateProfileInput): ProfileChanges {
    const fullName = update.fullName ?? current.fullName;
    const phone = update.phone ?? current.phone;
    const contactEmail = update.contactEmail ?? current.contactEmail;
    if (!contactEmail || !isEmail(contactEmail)) throw new ProfileError(ProfileFailure.ContactEmailRequired);
    const completed =
        !!fullName?.trim() &&
        Array.from(fullName).length <= PROFILE_LIMITS.fullName &&
        !/\p{Cc}/u.test(fullName) &&
        !!phone &&
        isValidPhone(phone);
    return { fullName, phone, contactEmail, onboardingStatus: completed ? 'COMPLETED' : 'PENDING' };
}
