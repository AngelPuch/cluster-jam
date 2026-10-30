import { Inject, Injectable } from '@nestjs/common';
import { ADDRESS_BOOK_REPOSITORY_PORT, type AddressBookRepositoryPort } from '../ports/address-book-repository.port';
import type { CreateAddressInput, OwnerAddress, UpdateAddressInput } from './address';
import { AddressError, AddressFailure } from './address.error';
import { normalizeCreateAddress, normalizeUpdateAddress } from './address-rules';
import { requireAddress } from './get-my-addresses.service';
import { ProfileError, ProfileFailure } from '../profile/profile.error';

function checkRevision(actual: string, expected: string): void {
    if (actual !== expected) throw new AddressError(AddressFailure.RevisionMismatch);
}

@Injectable()
export class ManageMyAddressesService {
    constructor(@Inject(ADDRESS_BOOK_REPOSITORY_PORT) private readonly addresses: AddressBookRepositoryPort) {}

    async create(userId: string, input: CreateAddressInput, expectedRevision: string): Promise<OwnerAddress> {
        const fields = normalizeCreateAddress(input);
        const result = await this.addresses.change(userId, (book) => {
            checkRevision(book.revision, expectedRevision);
            return { kind: 'create', fields };
        });
        if (!result) throw new ProfileError(ProfileFailure.NotReady);
        return requireAddress(result.book, result.affectedAddressId);
    }
    async update(
        userId: string,
        addressId: string,
        input: UpdateAddressInput,
        expectedRevision: string,
    ): Promise<OwnerAddress> {
        const fields = normalizeUpdateAddress(input);
        const result = await this.addresses.change(userId, (book) => {
            checkRevision(requireAddress(book, addressId).revision, expectedRevision);
            return { kind: 'update', addressId, fields };
        });
        if (!result) throw new ProfileError(ProfileFailure.NotReady);
        return requireAddress(result.book, addressId);
    }
    async delete(userId: string, addressId: string, expectedRevision: string): Promise<void> {
        const result = await this.addresses.change(userId, (book) => {
            checkRevision(requireAddress(book, addressId).revision, expectedRevision);
            return { kind: 'delete', addressId };
        });
        if (!result) throw new ProfileError(ProfileFailure.NotReady);
    }
}
