import { ApiProperty } from '@nestjs/swagger';
import { IsEmail, MaxLength } from 'class-validator';

export class RequestEmailConfirmationDto {
    @ApiProperty({ example: 'user@example.com', maxLength: 254 })
    @IsEmail()
    @MaxLength(254)
    email!: string;
}
