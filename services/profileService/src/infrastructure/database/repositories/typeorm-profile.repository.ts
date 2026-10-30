import { Injectable } from '@nestjs/common';
import { createHash } from 'node:crypto';
import { DataSource } from 'typeorm';
import type { CustomerProfile, ProfileChanges } from '../../../application/profile/profile';
import type { ProfileRepositoryPort } from '../../../application/ports/profile-repository.port';
import { ProfileError, ProfileFailure } from '../../../application/profile/profile.error';
import { OnboardingStatus, ProfileEntity } from '../entities/profile.entity';

function snapshot(entity: ProfileEntity): CustomerProfile {
    const revision = createHash('sha256')
        .update(
            JSON.stringify([
                entity.userId,
                entity.name,
                entity.phone,
                entity.contactEmail,
                entity.onboardingStatus,
                entity.createdAt.toISOString(),
                entity.updatedAt.toISOString(),
            ]),
        )
        .digest('hex');
    return {
        userId: entity.userId,
        fullName: entity.name,
        phone: entity.phone,
        contactEmail: entity.contactEmail,
        onboardingStatus: entity.onboardingStatus,
        createdAt: entity.createdAt,
        updatedAt: entity.updatedAt,
        revision,
    };
}

function persistenceFailure(error: unknown): never {
    if (error instanceof ProfileError) throw error;
    throw new ProfileError(ProfileFailure.PersistenceUnavailable);
}

@Injectable()
export class TypeormProfileRepository implements ProfileRepositoryPort {
    constructor(private readonly dataSource: DataSource) {}

    async findByUserId(userId: string): Promise<CustomerProfile | null> {
        try {
            const row = await this.dataSource.getRepository(ProfileEntity).findOneBy({ userId });
            return row ? snapshot(row) : null;
        } catch (error) {
            return persistenceFailure(error);
        }
    }

    async update(
        userId: string,
        change: (current: CustomerProfile) => ProfileChanges,
    ): Promise<CustomerProfile | null> {
        try {
            return await this.dataSource.transaction(async (manager) => {
                const repository = manager.getRepository(ProfileEntity);
                const row = await repository.findOne({ where: { userId }, lock: { mode: 'pessimistic_write' } });
                if (!row) return null;
                const changes = change(snapshot(row));
                row.name = changes.fullName;
                row.phone = changes.phone;
                row.contactEmail = changes.contactEmail;
                row.onboardingStatus =
                    changes.onboardingStatus === 'COMPLETED' ? OnboardingStatus.COMPLETED : OnboardingStatus.PENDING;
                return snapshot(await repository.save(row));
            });
        } catch (error) {
            return persistenceFailure(error);
        }
    }
}
