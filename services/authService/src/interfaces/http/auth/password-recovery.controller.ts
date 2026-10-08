import {
    Body,
    Controller,
    Header,
    HttpCode,
    HttpStatus,
    Post,
} from '@nestjs/common';
import {
    ApiNoContentResponse,
    ApiOkResponse,
    ApiOperation,
    ApiResponse,
    ApiTags,
    getSchemaPath,
} from '@nestjs/swagger';

import { PasswordRecoveryService } from '../../../application/auth/password-recovery.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import {
    PASSWORD_RECOVERY_MESSAGE,
    PasswordRecoveryRequestResponseDto,
} from './dto/password-recovery-request-response.dto';
import { RecoverPasswordDto } from './dto/recover-password.dto';
import { RequestPasswordRecoveryDto } from './dto/request-password-recovery.dto';
import { throwPasswordRecoveryHttpError } from './password-recovery-error.mapper';

const problemContent = {
    'application/problem+json': {
        schema: { $ref: getSchemaPath(ProblemDetailsDto) },
    },
};

@ApiTags('Authentication')
@Controller()
export class PasswordRecoveryController {
    constructor(private readonly service: PasswordRecoveryService) {}

    @Post('password-recovery-requests')
    @Header('Cache-Control', 'no-store')
    @HttpCode(HttpStatus.OK)
    @ApiOperation({
        summary: 'Request a password recovery email',
        description:
            'Always returns a neutral result for valid input. This does not confirm account existence or email delivery.',
    })
    @ApiOkResponse({ type: PasswordRecoveryRequestResponseDto })
    @ApiResponse({
        status: HttpStatus.UNPROCESSABLE_ENTITY,
        description: 'Invalid email or unexpected request fields.',
        content: problemContent,
    })
    async request(
        @Body() dto: RequestPasswordRecoveryDto,
    ): Promise<PasswordRecoveryRequestResponseDto> {
        await this.service.request(dto.email);
        return { message: PASSWORD_RECOVERY_MESSAGE };
    }

    @Post('password-recoveries')
    @Header('Cache-Control', 'no-store')
    @HttpCode(HttpStatus.NO_CONTENT)
    @ApiOperation({
        summary: 'Recover a password using an email code',
        description:
            'Verifies email and a six-digit recovery code with Supabase, then updates the password. A login Bearer token does not replace the recovery code. After verification the code is consumed, even if the update fails.',
    })
    @ApiNoContentResponse({ description: 'The password was updated.' })
    @ApiResponse({
        status: HttpStatus.UNAUTHORIZED,
        description: 'Invalid, expired or already used recovery code.',
        content: problemContent,
    })
    @ApiResponse({
        status: HttpStatus.FORBIDDEN,
        description:
            'Recovery is blocked or additional verification is required by Supabase.',
        content: problemContent,
    })
    @ApiResponse({
        status: HttpStatus.CONFLICT,
        description: 'The new password is the same as the current password.',
        content: problemContent,
    })
    @ApiResponse({
        status: HttpStatus.UNPROCESSABLE_ENTITY,
        description: 'Invalid fields or rejected password policy.',
        content: problemContent,
    })
    @ApiResponse({
        status: HttpStatus.TOO_MANY_REQUESTS,
        description: 'Recovery verification or update was rate limited.',
        content: problemContent,
    })
    @ApiResponse({
        status: HttpStatus.SERVICE_UNAVAILABLE,
        description: 'Supabase Auth is unavailable or returned invalid data.',
        content: problemContent,
    })
    async recover(@Body() dto: RecoverPasswordDto): Promise<void> {
        try {
            await this.service.recover(dto);
        } catch (error) {
            throwPasswordRecoveryHttpError(error);
        }
    }
}
