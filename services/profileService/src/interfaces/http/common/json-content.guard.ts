import { Injectable, type CanActivate, type ExecutionContext } from '@nestjs/common';
import type { Request } from 'express';
import { requireJson } from './conditional-request';

// Method guard: runs after owner authentication and before DTO validation.
@Injectable()
export class JsonContentGuard implements CanActivate {
    canActivate(context: ExecutionContext): boolean {
        requireJson(context.switchToHttp().getRequest<Request>().headers['content-type']);
        return true;
    }
}
