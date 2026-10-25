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

export interface RecoverPasswordInput {
  email: string;
  code: string;
  newPassword: string;
}

export interface ConfirmEmailInput {
  email: string;
  code: string;
}

export interface AuthProviderPort {
  isAvailable(): Promise<boolean>;

  registerUser(input: RegisterUserInput): Promise<RegisterUserResult>;

  confirmEmail(input: ConfirmEmailInput): Promise<LoginUserResult>;

  resendEmailConfirmation(email: string): Promise<void>;

  loginUser(input: LoginUserInput): Promise<LoginUserResult>;

  refreshSession(input: RefreshSessionInput): Promise<RefreshSessionResult>;

  requestPasswordRecovery(email: string): Promise<void>;

  recoverPassword(input: RecoverPasswordInput): Promise<void>;
}
