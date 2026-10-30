import { Transform } from 'class-transformer';
import { IsBoolean, IsISO31661Alpha2, IsNotEmpty, IsOptional, IsString, MaxLength, ValidateIf } from 'class-validator';
import { ApiProperty, ApiPropertyOptional, PartialType } from '@nestjs/swagger';
import { ADDRESS_TEXT_LIMITS as limits } from '../../../../application/addresses/address-rules';
import type { CreateAddressInput, OwnerAddress } from '../../../../application/addresses/address';

const trim = ({ value }: { value: unknown }): unknown => (typeof value === 'string' ? value.trim() : value);
const countryCode = ({ value }: { value: unknown }): unknown =>
    typeof value === 'string' ? value.trim().toUpperCase() : value;

export class CreateAddressDto implements CreateAddressInput {
    @ApiProperty({ example: 'Casa', maxLength: limits.label, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.label)
    label!: string;

    @ApiProperty({ example: 'María López', maxLength: limits.recipient, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.recipient)
    recipient!: string;

    @ApiProperty({ example: 'Avenida Reforma', maxLength: limits.street, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.street)
    street!: string;

    @ApiProperty({ example: '123', maxLength: limits.exteriorNumber, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.exteriorNumber)
    exteriorNumber!: string;

    @ApiPropertyOptional({
        type: String,
        nullable: true,
        example: '4B',
        maxLength: limits.interiorNumber,
        description: 'Omit to preserve on PATCH; null explicitly clears it. Blank strings are rejected.',
    })
    @Transform(trim)
    @IsOptional()
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.interiorNumber)
    interiorNumber?: string | null;

    @ApiProperty({ example: 'Centro', maxLength: limits.neighborhood, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.neighborhood)
    neighborhood!: string;

    @ApiProperty({ example: 'Cuauhtémoc', maxLength: limits.municipality, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.municipality)
    municipality!: string;

    @ApiProperty({ example: 'Ciudad de México', maxLength: limits.state, minLength: 1 })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.state)
    state!: string;

    @ApiProperty({
        example: '06000',
        maxLength: limits.postalCode,
        minLength: 1,
        description:
            'Nonblank text within the existing 5-character schema; leading zeroes are preserved. No shipping/geocoding validation.',
    })
    @Transform(trim)
    @IsString()
    @IsNotEmpty()
    @MaxLength(limits.postalCode)
    postalCode!: string;

    @ApiProperty({
        example: 'MX',
        minLength: 2,
        maxLength: limits.country,
        description: 'ISO 3166-1 alpha-2 country code, normalized to uppercase.',
    })
    @Transform(countryCode)
    @IsString()
    @IsISO31661Alpha2()
    @MaxLength(limits.country)
    country!: string;

    @ApiPropertyOptional({
        example: false,
        default: false,
        description:
            'True explicitly selects this address and unsets the previous default. No automatic default selection.',
    })
    @ValidateIf((_object, value: unknown) => value !== undefined)
    @IsBoolean()
    isDefault?: boolean;
}

export class UpdateAddressDto extends PartialType(CreateAddressDto, { skipNullProperties: false }) {}

export class AddressResponseDto extends CreateAddressDto {
    @ApiProperty({ format: 'uuid', example: '22222222-2222-4222-8222-222222222222' }) id!: string;
    @ApiProperty({ type: String, required: true, nullable: true, example: null, maxLength: limits.interiorNumber })
    declare interiorNumber: string | null;
    @ApiProperty({ required: true, example: false }) declare isDefault: boolean;

    static from(address: OwnerAddress): AddressResponseDto {
        return {
            id: address.id,
            label: address.label,
            recipient: address.recipient,
            street: address.street,
            exteriorNumber: address.exteriorNumber,
            interiorNumber: address.interiorNumber,
            neighborhood: address.neighborhood,
            municipality: address.municipality,
            state: address.state,
            postalCode: address.postalCode,
            country: address.country,
            isDefault: address.isDefault,
        };
    }
}

export class AddressListResponseDto {
    @ApiProperty({ type: () => [AddressResponseDto] }) items!: AddressResponseDto[];
}
