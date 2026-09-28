import { ApiProperty } from '@nestjs/swagger';
import { IsEmail, IsNotEmpty, IsString, MaxLength } from 'class-validator';

export class LoginUserDto {
    @ApiProperty({
        example: 'user@example.com',
        maxLength: 254,
    })
    @IsEmail()
    @MaxLength(254)
    email!: string;

    @ApiProperty({
        example: 'StrongPassword123!',
        writeOnly: true,
    })
    @IsString()
    @IsNotEmpty()
    password!: string;
}
