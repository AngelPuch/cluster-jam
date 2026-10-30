import type { CustomerProfile, ProfileChanges } from '../profile/profile';

export const PROFILE_REPOSITORY_PORT = Symbol('PROFILE_REPOSITORY_PORT');

export interface ProfileRepositoryPort {
    findByUserId: (userId: string) => Promise<CustomerProfile | null>;
    update: (userId: string, change: (current: CustomerProfile) => ProfileChanges) => Promise<CustomerProfile | null>;
}
