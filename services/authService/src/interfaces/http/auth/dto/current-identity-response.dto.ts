import { ApiProperty } from '@nestjs/swagger';
import { AppRole } from '../../../../application/auth/app-role';

export class CurrentIdentityResponseDto {
  @ApiProperty({
    format: 'uuid',
    example: '11111111-1111-4111-8111-111111111111',
  })
  userId!: string;

  @ApiProperty({ example: 'user@example.com' })
  email!: string;

  @ApiProperty({ enum: AppRole, example: AppRole.Client })
  appRole!: AppRole;
}
