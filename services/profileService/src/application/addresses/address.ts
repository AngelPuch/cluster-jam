export interface AddressFields {
    readonly label: string;
    readonly recipient: string;
    readonly street: string;
    readonly exteriorNumber: string;
    readonly interiorNumber: string | null;
    readonly neighborhood: string;
    readonly municipality: string;
    readonly state: string;
    readonly postalCode: string;
    readonly country: string;
    readonly isDefault: boolean;
}

export type CreateAddressInput = Omit<AddressFields, 'interiorNumber' | 'isDefault'> & {
    readonly interiorNumber?: string | null;
    readonly isDefault?: boolean;
};
export type UpdateAddressInput = Partial<AddressFields>;
export interface OwnerAddress extends AddressFields {
    readonly id: string;
    readonly revision: string;
}
export interface AddressBook {
    readonly items: readonly OwnerAddress[];
    readonly revision: string;
}
export type AddressChange =
    | { readonly kind: 'create'; readonly fields: AddressFields }
    | { readonly kind: 'update'; readonly addressId: string; readonly fields: UpdateAddressInput }
    | { readonly kind: 'delete'; readonly addressId: string };
