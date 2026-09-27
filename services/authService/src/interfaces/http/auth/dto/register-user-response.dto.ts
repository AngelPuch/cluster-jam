import { ApiProperty } from '@nestjs/swagger';

import { UserRegistrationStatus } from '../../../../application/ports/auth-provider.port';

export class RegisterUserResponseDto {
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
        enum: UserRegistrationStatus,
        example: UserRegistrationStatus.PendingEmailConfirmation,
    })
    status!: UserRegistrationStatus;
}
