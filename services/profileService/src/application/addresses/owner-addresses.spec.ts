import { jest } from '@jest/globals';
import type { AddressBookRepositoryPort } from '../ports/address-book-repository.port';
import type { AddressBook, CreateAddressInput } from './address';
import { GetMyAddressesService } from './get-my-addresses.service';
import { ManageMyAddressesService } from './manage-my-addresses.service';
import { AddressError, AddressFailure } from './address.error';
import { ProfileError, ProfileFailure } from '../profile/profile.error';

describe('Owner address use cases', () => {
    const fields: CreateAddressInput = {
        label: 'Casa',
        recipient: 'María',
        street: 'Reforma',
        exteriorNumber: '123',
        neighborhood: 'Centro',
        municipality: 'Cuauhtémoc',
        state: 'CDMX',
        postalCode: '06000',
        country: 'MX',
    };
    const book: AddressBook = {
        revision: 'book',
        items: [{ ...fields, interiorNumber: null, isDefault: false, id: 'owned', revision: 'item' }],
    };
    const read = jest.fn<AddressBookRepositoryPort['read']>();
    const change = jest.fn<AddressBookRepositoryPort['change']>();
    const port = { read, change };
    const reads = new GetMyAddressesService(port);
    const writes = new ManageMyAddressesService(port);
    beforeEach(() => {
        read.mockReset();
        change.mockReset();
    });

    it('lists only the verified owner and hides foreign/missing addresses identically', async () => {
        read.mockResolvedValue(book);
        await expect(reads.list('owner')).resolves.toBe(book);
        expect(read).toHaveBeenCalledWith('owner');
        await expect(reads.get('owner', 'owned')).resolves.toBe(book.items[0]);
        await expect(reads.get('owner', 'foreign')).rejects.toThrow(new AddressError(AddressFailure.NotFound));
    });
    it('does not provision an absent owner for any operation', async () => {
        read.mockResolvedValue(null);
        change.mockResolvedValue(null);
        for (const operation of [
            reads.list('missing'),
            writes.create('missing', fields, 'book'),
            writes.update('missing', 'owned', { label: 'Office' }, 'item'),
            writes.delete('missing', 'owned', 'item'),
        ]) {
            await expect(operation).rejects.toThrow(new ProfileError(ProfileFailure.NotReady));
        }
    });
    it('rejects stale collection/item revisions and hidden IDs inside the transaction decision', async () => {
        change.mockImplementation((_owner, decide) => {
            decide(book);
            return Promise.resolve({ book, affectedAddressId: 'owned' });
        });
        await expect(writes.create('owner', fields, 'stale')).rejects.toThrow(
            new AddressError(AddressFailure.RevisionMismatch),
        );
        await expect(writes.update('owner', 'owned', { label: 'Office' }, 'book')).rejects.toThrow(
            new AddressError(AddressFailure.RevisionMismatch),
        );
        await expect(writes.delete('owner', 'owned', 'stale')).rejects.toThrow(
            new AddressError(AddressFailure.RevisionMismatch),
        );
        await expect(writes.update('owner', 'foreign', { label: 'Office' }, 'stale')).rejects.toThrow(
            new AddressError(AddressFailure.NotFound),
        );
        await expect(writes.delete('owner', 'foreign', 'stale')).rejects.toThrow(
            new AddressError(AddressFailure.NotFound),
        );
    });
    it('rejects invalid inputs before asking the repository to change anything', async () => {
        await expect(writes.create('owner', {} as CreateAddressInput, 'book')).rejects.toThrow(AddressError);
        await expect(writes.update('owner', 'owned', {}, 'item')).rejects.toThrow(AddressError);
        expect(change).not.toHaveBeenCalled();
    });
});
