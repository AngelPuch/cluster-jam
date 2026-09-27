export const AUTH_PROVIDER_PORT = Symbol('AUTH_PROVIDER_PORT');

export interface AuthProviderPort {
    isAvailable(): Promise<boolean>;
}
