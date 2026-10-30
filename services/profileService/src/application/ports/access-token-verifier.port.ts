import type { VerifiedIdentity } from '../security/verified-identity';

export const ACCESS_TOKEN_VERIFIER_PORT = Symbol('ACCESS_TOKEN_VERIFIER_PORT');
export const MAX_ACCESS_TOKEN_LENGTH = 16384;

export interface AccessTokenVerifierPort {
    verify: (accessToken: string) => Promise<VerifiedIdentity>;
}
