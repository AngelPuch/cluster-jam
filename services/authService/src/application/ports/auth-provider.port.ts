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

export interface LoginUserInput {
    email: string;
    password: string;
}

export interface LoginUserResult {
    userId: string;
    email: string;
    accessToken: string;
    refreshToken: string;
    expiresIn: number;
    tokenType: string;
}

export interface RefreshSessionInput {
    refreshToken: string;
}

export type RefreshSessionResult = LoginUserResult;

export interface AuthProviderPort {
    isAvailable(): Promise<boolean>;

    registerUser(input: RegisterUserInput): Promise<RegisterUserResult>;

    loginUser(input: LoginUserInput): Promise<LoginUserResult>;

    refreshSession(input: RefreshSessionInput): Promise<RefreshSessionResult>;
}
