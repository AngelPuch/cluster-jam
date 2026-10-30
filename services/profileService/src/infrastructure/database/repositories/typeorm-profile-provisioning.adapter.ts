import { Injectable } from '@nestjs/common';
import { DataSource } from 'typeorm';
import type {
    MinimumProfileInput,
    ProfileProvisioningPort,
    ProfileProvisioningResult,
} from '../../../application/ports/profile-provisioning.port';

@Injectable()
export class TypeormProfileProvisioningAdapter implements ProfileProvisioningPort {
    constructor(private readonly dataSource: DataSource) {}

    async provision(input: MinimumProfileInput): Promise<ProfileProvisioningResult> {
        return this.dataSource.transaction(async (manager) => {
            const inserted = await manager.query<Array<{ event_id: string }>>(
                `INSERT INTO app.inbox_messages (event_id, event_type)
                 VALUES ($1, $2) ON CONFLICT (event_id) DO NOTHING RETURNING event_id`,
                [input.eventId, 'identity.user.registered'],
            );
            if (inserted.length === 0) return { status: 'duplicate' };

            const profiles = await manager.query<Array<{ user_id: string }>>(
                `INSERT INTO app.profile
                     (user_id, contact_email, name, phone, onboarding_status)
                 VALUES ($1, $2, NULL, NULL, 'PENDING')
                 ON CONFLICT (user_id) DO NOTHING RETURNING user_id`,
                [input.userId, input.initialContactEmail],
            );
            return { status: 'processed', profileCreated: profiles.length === 1 };
        });
    }
}
