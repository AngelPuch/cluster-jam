import { Inject, Injectable } from '@nestjs/common';
import { ADDRESS_BOOK_REPOSITORY_PORT, type AddressBookRepositoryPort } from '../ports/address-book-repository.port';
import type { AddressBook, OwnerAddress } from './address';
import { AddressError, AddressFailure } from './address.error';
import { ProfileError, ProfileFailure } from '../profile/profile.error';

export function requireAddress(book: AddressBook, addressId: string): OwnerAddress {
    const address = book.items.find((item) => item.id === addressId.toLowerCase());
    if (!address) throw new AddressError(AddressFailure.NotFound);
    return address;
}

@Injectable()
export class GetMyAddressesService {
    constructor(@Inject(ADDRESS_BOOK_REPOSITORY_PORT) private readonly addresses: AddressBookRepositoryPort) {}

    async list(userId: string): Promise<AddressBook> {
        const book = await this.addresses.read(userId);
        if (!book) throw new ProfileError(ProfileFailure.NotReady);
        return book;
    }
    async get(userId: string, addressId: string): Promise<OwnerAddress> {
        return requireAddress(await this.list(userId), addressId);
    }
}
