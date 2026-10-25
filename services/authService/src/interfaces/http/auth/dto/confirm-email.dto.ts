import { ApiProperty } from '@nestjs/swagger';
import { IsEmail, IsString, Matches, MaxLength } from 'class-validator';

export class ConfirmEmailDto {
    @ApiProperty({ example: 'user@example.com', maxLength: 254 })
    @IsEmail()
    @MaxLength(254)
    email!: string;

    @ApiProperty({
        description: 'Six-digit code from the signup confirmation email.',
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
}
