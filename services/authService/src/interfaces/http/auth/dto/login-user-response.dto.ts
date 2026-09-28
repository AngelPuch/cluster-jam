import { ApiProperty } from '@nestjs/swagger';

export class LoginUserResponseDto {
    @ApiProperty({
        format: 'uuid',
        example: '11111111-1111-4111-8111-111111111111',
    })
    userId!: string;

    @ApiProperty({
        example: 'user@example.com',
    })
    email!: string;

    @ApiProperty({
        description: 'Supabase access token.',
        example: 'access-token',
    })
    accessToken!: string;

    @ApiProperty({
        description: 'Supabase refresh token.',
        example: 'refresh-token',
    })
    refreshToken!: string;

    @ApiProperty({
        description: 'Access token lifetime in seconds.',
        example: 3600,
    })
    expiresIn!: number;

    @ApiProperty({
        example: 'bearer',
    })
    tokenType!: string;
}
