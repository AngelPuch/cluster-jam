export type ProfileOnboardingStatus = 'PENDING' | 'COMPLETED';

export interface CustomerProfile {
    readonly userId: string;
    readonly fullName: string | null;
    readonly phone: string | null;
    readonly contactEmail: string | null;
    readonly onboardingStatus: ProfileOnboardingStatus;
    readonly createdAt: Date;
    readonly updatedAt: Date;
    readonly revision: string;
}

export interface UpdateProfileInput {
    readonly fullName?: string;
    readonly phone?: string;
    readonly contactEmail?: string;
}

export interface ProfileChanges {
    fullName: string | null;
    phone: string | null;
    contactEmail: string;
    onboardingStatus: ProfileOnboardingStatus;
}
