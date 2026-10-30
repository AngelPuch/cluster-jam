export enum AppRole {
    Client = 'cliente',
    Administrator = 'administrador',
}

export interface VerifiedIdentity {
    readonly userId: string;
    readonly appRole: AppRole;
}
