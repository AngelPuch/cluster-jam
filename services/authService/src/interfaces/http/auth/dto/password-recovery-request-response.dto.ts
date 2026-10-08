import { ApiProperty } from '@nestjs/swagger';

export const PASSWORD_RECOVERY_MESSAGE =
    'If the account can receive recovery emails, you will receive instructions.';

export class PasswordRecoveryRequestResponseDto {
    @ApiProperty({ example: PASSWORD_RECOVERY_MESSAGE })
    message!: string;
}
