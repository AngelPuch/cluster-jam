import { Injectable } from '@nestjs/common';
import { createHash } from 'node:crypto';
import { DataSource, type EntityManager } from 'typeorm';
import type {
    AddressBookRepositoryPort,
    AddressMutationResult,
} from '../../../application/ports/address-book-repository.port';
import type { AddressBook, AddressChange, AddressFields } from '../../../application/addresses/address';
import { AddressError, AddressFailure } from '../../../application/addresses/address.error';
import { ProfileError } from '../../../application/profile/profile.error';
import { AddressEntity } from '../entities/address.entity';
import { ProfileEntity } from '../entities/profile.entity';

function fields(row: AddressEntity): AddressFields {
    return {
        label: row.label,
        recipient: row.recipient,
        street: row.street,
        exteriorNumber: row.exteriorNumber,
        interiorNumber: row.interiorNumber,
        neighborhood: row.neighborhood,
        municipality: row.municipality,
        state: row.state,
        postalCode: row.postalCode,
        country: row.country,
        isDefault: row.isDefault,
    };
}
function hash(value: unknown): string {
    return createHash('sha256').update(JSON.stringify(value)).digest('hex');
}
function snapshot(userId: string, rows: AddressEntity[]): AddressBook {
    const items = rows.map((row) => ({ id: row.id, ...fields(row) }));
    const revision = hash([userId, items]);
    return { revision, items: items.map((item) => ({ ...item, revision: hash([revision, item.id]) })) };
}
function persistenceFailure(error: unknown): never {
    if (error instanceof AddressError || error instanceof ProfileError) throw error;
    throw new AddressError(AddressFailure.PersistenceUnavailable);
}

@Injectable()
export class TypeormAddressBookRepository implements AddressBookRepositoryPort {
    constructor(private readonly dataSource: DataSource) {}

    async read(userId: string): Promise<AddressBook | null> {
        try {
            return await this.dataSource.transaction(async (manager) => {
                if (!(await this.lockOwner(manager, userId, 'pessimistic_read'))) return null;
                return this.readBook(manager, userId);
            });
        } catch (error) {
            return persistenceFailure(error);
        }
    }
    async change(
        userId: string,
        decide: (current: AddressBook) => AddressChange,
    ): Promise<AddressMutationResult | null> {
        try {
            return await this.dataSource.transaction(async (manager) => {
                if (!(await this.lockOwner(manager, userId, 'pessimistic_write'))) return null;
                const command = decide(await this.readBook(manager, userId));
                const repository = manager.getRepository(AddressEntity);
                let affectedAddressId: string;
                if (command.kind === 'delete') {
                    await repository.delete({ id: command.addressId, userId });
                    affectedAddressId = command.addressId;
                } else {
                    if (command.fields.isDefault === true) {
                        await repository.update({ userId, isDefault: true }, { isDefault: false });
                    }
                    if (command.kind === 'create') {
                        const row = await repository.save(repository.create({ ...command.fields, userId }));
                        affectedAddressId = row.id;
                    } else {
                        await repository.update({ id: command.addressId, userId }, { ...command.fields });
                        affectedAddressId = command.addressId;
                    }
                }
                return { book: await this.readBook(manager, userId), affectedAddressId };
            });
        } catch (error) {
            return persistenceFailure(error);
        }
    }
    private lockOwner(manager: EntityManager, userId: string, mode: 'pessimistic_read' | 'pessimistic_write') {
        return manager.getRepository(ProfileEntity).findOne({ where: { userId }, lock: { mode } });
    }
    private async readBook(manager: EntityManager, userId: string): Promise<AddressBook> {
        return snapshot(
            userId,
            await manager.getRepository(AddressEntity).find({ where: { userId }, order: { id: 'ASC' } }),
        );
    }
}
