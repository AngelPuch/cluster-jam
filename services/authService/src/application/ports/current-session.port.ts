import type { AppRole } from '../auth/app-role';

export const CURRENT_SESSION_PORT = Symbol('CURRENT_SESSION_PORT');

export interface CurrentIdentity {
    userId: string;
    email: string;
    appRole: AppRole;
}

export interface CurrentSessionPort {
    getCurrentIdentity(accessToken: string): Promise<CurrentIdentity>;
    endCurrentSession(accessToken: string): Promise<void>;
}
