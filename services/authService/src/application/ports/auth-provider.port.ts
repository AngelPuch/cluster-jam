export const AUTH_PROVIDER_PORT = Symbol('AUTH_PROVIDER_PORT');

export enum UserRegistrationStatus {
    PendingEmailConfirmation = 'PENDING_EMAIL_CONFIRMATION',
    Active = 'ACTIVE',
}

export interface RegisterUserInput {
    email: string;
    password: string;
}

export interface RegisterUserResult {
    userId: string;
    email: string;
    status: UserRegistrationStatus;
}

export interface AuthProviderPort {
    isAvailable(): Promise<boolean>;

    registerUser(input: RegisterUserInput): Promise<RegisterUserResult>;
}
