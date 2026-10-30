import type { AddressBook, AddressChange } from '../addresses/address';

export const ADDRESS_BOOK_REPOSITORY_PORT = Symbol('ADDRESS_BOOK_REPOSITORY_PORT');
export interface AddressMutationResult {
    readonly book: AddressBook;
    readonly affectedAddressId: string;
}
export interface AddressBookRepositoryPort {
    read(userId: string): Promise<AddressBook | null>;
    change(userId: string, decide: (current: AddressBook) => AddressChange): Promise<AddressMutationResult | null>;
}
