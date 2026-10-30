export const PROFILE_PROVISIONING_PORT = Symbol('PROFILE_PROVISIONING_PORT');

export interface MinimumProfileInput {
    readonly eventId: string;
    readonly userId: string;
    readonly initialContactEmail: string;
}

export type ProfileProvisioningResult = { status: 'processed'; profileCreated: boolean } | { status: 'duplicate' };

export interface ProfileProvisioningPort {
    provision(input: MinimumProfileInput): Promise<ProfileProvisioningResult>;
}
