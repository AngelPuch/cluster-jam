import { ApiProperty } from '@nestjs/swagger';

export const EMAIL_CONFIRMATION_MESSAGE =
  'If the account is pending confirmation, a confirmation code will be sent.';

export class EmailConfirmationRequestResponseDto {
  @ApiProperty({ example: EMAIL_CONFIRMATION_MESSAGE })
  message!: string;
}
