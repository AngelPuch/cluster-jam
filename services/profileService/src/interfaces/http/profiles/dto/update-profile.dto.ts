import { Transform } from 'class-transformer';
import { IsEmail, IsNotEmpty, IsString, MaxLength, ValidateIf } from 'class-validator';
import { ApiPropertyOptional } from '@nestjs/swagger';
import { PROFILE_LIMITS } from '../../../../application/profile/profile-rules';

const trim = ({ value }: { value: unknown }): unknown => (typeof value === 'string' ? value.trim() : value);

export class UpdateProfileDto {
    @ApiPropertyOptional({
        example: 'María López',
        maxLength: PROFILE_LIMITS.fullName,
        description: 'Nonblank name; surrounding whitespace is removed. Null is not accepted.',
    })
    @Transform(trim)
    @ValidateIf((_object, value: unknown) => value !== undefined)
    @IsString()
    @IsNotEmpty()
    @MaxLength(PROFILE_LIMITS.fullName)
    fullName?: string;

    @ApiPropertyOptional({
        example: '+52 55 1234 5678',
        maxLength: PROFILE_LIMITS.phone,
        description:
            '7–15 digits with optional leading + and spaces, parentheses, dots or hyphens. Null is not accepted.',
    })
    @Transform(trim)
    @ValidateIf((_object, value: unknown) => value !== undefined)
    @IsString()
    @IsNotEmpty()
    @MaxLength(PROFILE_LIMITS.phone)
    phone?: string;

    @ApiPropertyOptional({
        example: 'contact@example.com',
        format: 'email',
        maxLength: PROFILE_LIMITS.contactEmail,
        description: 'Business contact address, independent from the Supabase login email. Null is not accepted.',
    })
    @Transform(trim)
    @ValidateIf((_object, value: unknown) => value !== undefined)
    @IsString()
    @IsEmail()
    @MaxLength(PROFILE_LIMITS.contactEmail)
    contactEmail?: string;
}
