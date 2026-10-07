import {
    Controller,
    Delete,
    Get,
    Header,
    Headers,
    HttpCode,
    HttpStatus,
    UnauthorizedException,
} from '@nestjs/common';
import {
    ApiBearerAuth,
    ApiNoContentResponse,
    ApiOkResponse,
    ApiOperation,
    ApiResponse,
    ApiTags,
} from '@nestjs/swagger';

import { CurrentSessionService } from '../../../application/auth/current-session.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwCurrentSessionHttpError } from './current-session-error.mapper';
import { CurrentIdentityResponseDto } from './dto/current-identity-response.dto';

@ApiTags('Authentication')
@ApiBearerAuth('supabase-jwt')
@Controller('sessions/current')
export class CurrentSessionController {
    constructor(private readonly sessions: CurrentSessionService) {}

    @Get()
    @Header('Cache-Control', 'no-store')
    @ApiOperation({
        summary: 'Get the current identity',
        description:
            'Checks the current Supabase session and returns its user ID and email.',
    })
    @ApiOkResponse({ type: CurrentIdentityResponseDto })
    @ApiResponse({ status: 401, type: ProblemDetailsDto })
    @ApiResponse({ status: 429, type: ProblemDetailsDto })
    @ApiResponse({ status: 503, type: ProblemDetailsDto })
    async getIdentity(
        @Headers('authorization') authorization?: string,
    ): Promise<CurrentIdentityResponseDto> {
        try {
            return await this.sessions.getIdentity(
                readBearerToken(authorization),
            );
        } catch (error) {
            throwCurrentSessionHttpError(error);
        }
    }

    @Delete()
    @HttpCode(HttpStatus.NO_CONTENT)
    @Header('Cache-Control', 'no-store')
    @ApiOperation({
        summary: 'End the current session',
        description:
            'Revokes only this Supabase session. The client must discard its tokens.',
    })
    @ApiNoContentResponse({ description: 'The current session was ended.' })
    @ApiResponse({ status: 401, type: ProblemDetailsDto })
    @ApiResponse({ status: 429, type: ProblemDetailsDto })
    @ApiResponse({ status: 503, type: ProblemDetailsDto })
    async end(@Headers('authorization') authorization?: string): Promise<void> {
        try {
            await this.sessions.end(readBearerToken(authorization));
        } catch (error) {
            throwCurrentSessionHttpError(error);
        }
    }
}

function readBearerToken(authorization?: string): string {
    const token = /^Bearer ([^\s]+)$/i.exec(authorization ?? '')?.[1];
    if (!token) {
        throw new UnauthorizedException({
            code: 'INVALID_ACCESS_TOKEN',
            detail: 'A Bearer access token is required.',
        });
    }
    return token;
}
