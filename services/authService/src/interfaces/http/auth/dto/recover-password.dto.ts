import { ApiProperty } from '@nestjs/swagger';
import {
    IsEmail,
    IsString,
    Matches,
    MaxLength,
    MinLength,
} from 'class-validator';

export class RecoverPasswordDto {
    @ApiProperty({ example: 'user@example.com', maxLength: 254 })
    @IsEmail()
    @MaxLength(254)
    email!: string;

    @ApiProperty({
        description: 'Six-digit code received in the password recovery email.',
        example: '012345',
        type: String,
        pattern: '^[0-9]{6}$',
        minLength: 6,
        maxLength: 6,
        writeOnly: true,
    })
    @IsString()
    @Matches(/^[0-9]{6}$/)
    code!: string;

    @ApiProperty({
        example: 'NewStrongPassword123!',
        minLength: 8,
        writeOnly: true,
    })
    @IsString()
    @MinLength(8)
    newPassword!: string;
}
