import { UnauthorizedException } from '@nestjs/common';

export function readBearerToken(authorization?: string): string {
  const token = /^Bearer ([^\s]+)$/i.exec(authorization ?? '')?.[1];
  if (!token) {
    throw new UnauthorizedException({
      code: 'INVALID_ACCESS_TOKEN',
      detail: 'A Bearer access token is required.',
    });
  }
  return token;
}
