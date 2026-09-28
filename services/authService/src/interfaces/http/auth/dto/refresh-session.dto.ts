import { ApiProperty } from '@nestjs/swagger';
import { IsNotEmpty, IsString, Matches, MaxLength } from 'class-validator';

export class RefreshSessionDto {
    @ApiProperty({
        description: 'Current Supabase refresh token.',
        example: 'refresh-token',
        maxLength: 4096,
        writeOnly: true,
    })
    @IsString()
    @IsNotEmpty()
    @MaxLength(4096)
    @Matches(/^\S+$/)
    refreshToken!: string;
}
