import { ApiProperty } from '@nestjs/swagger';
import { IsEmail, IsString, MaxLength, MinLength } from 'class-validator';

export class RegisterUserDto {
    @ApiProperty({
        example: 'user@example.com',
        maxLength: 254,
    })
    @IsEmail()
    @MaxLength(254)
    email!: string;

    @ApiProperty({
        example: 'StrongPassword123!',
        minLength: 8,
        writeOnly: true,
    })
    @IsString()
    @MinLength(8)
    password!: string;
}
