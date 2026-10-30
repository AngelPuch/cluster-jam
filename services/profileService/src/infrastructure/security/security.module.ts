import { Module } from '@nestjs/common';
import { APP_FILTER } from '@nestjs/core';
import { ACCESS_TOKEN_VERIFIER_PORT } from '../../application/ports/access-token-verifier.port';
import { JwtAuthGuard } from '../../interfaces/http/profiles/jwt-auth.guard';
import { SecurityExceptionFilter } from '../../interfaces/http/common/errors/security-exception.filter';
import { SupabaseJwtVerifier } from './supabase-jwt-verifier';

@Module({
    providers: [
        SupabaseJwtVerifier,
        { provide: ACCESS_TOKEN_VERIFIER_PORT, useExisting: SupabaseJwtVerifier },
        JwtAuthGuard,
        { provide: APP_FILTER, useClass: SecurityExceptionFilter },
    ],
    exports: [JwtAuthGuard, ACCESS_TOKEN_VERIFIER_PORT],
})
export class SecurityModule {}
