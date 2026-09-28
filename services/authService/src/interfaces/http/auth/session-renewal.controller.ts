import {
    Body,
    Controller,
    Header,
    HttpCode,
    HttpStatus,
    Post,
} from '@nestjs/common';
import {
    ApiOkResponse,
    ApiOperation,
    ApiResponse,
    ApiTags,
} from '@nestjs/swagger';

import { RefreshSessionService } from '../../../application/auth/refresh-session.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwAuthRefreshHttpError } from './auth-refresh-error.mapper';
import { LoginUserResponseDto } from './dto/login-user-response.dto';
import { RefreshSessionDto } from './dto/refresh-session.dto';

@ApiTags('Authentication')
@Controller('session-renewals')
export class SessionRenewalController {
    constructor(
        private readonly refreshSessionService: RefreshSessionService,
    ) {}

    @Post()
    @HttpCode(HttpStatus.OK)
    @Header('Cache-Control', 'no-store')
    @ApiOperation({
        summary: 'Renew a session',
        description:
            'Exchanges a Supabase refresh token for a new access token and refresh token.',
    })
    @ApiOkResponse({
        description: 'The session was renewed.',
        type: LoginUserResponseDto,
    })
    @ApiResponse({
        status: HttpStatus.UNAUTHORIZED,
        description: 'The refresh token is invalid or the session has ended.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.CONFLICT,
        description: 'A concurrent renewal conflicted with this request.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.UNPROCESSABLE_ENTITY,
        description: 'The renewal request is invalid.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.TOO_MANY_REQUESTS,
        description: 'The renewal request was rate limited.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.SERVICE_UNAVAILABLE,
        description: 'Supabase Auth is temporarily unavailable.',
        type: ProblemDetailsDto,
    })
    async renew(@Body() dto: RefreshSessionDto): Promise<LoginUserResponseDto> {
        try {
            return await this.refreshSessionService.execute(dto);
        } catch (error) {
            throwAuthRefreshHttpError(error);
        }
    }
}
