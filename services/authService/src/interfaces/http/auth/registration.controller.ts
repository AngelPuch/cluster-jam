import {
    Body,
    Controller,
    Header,
    HttpCode,
    HttpStatus,
    Post,
} from '@nestjs/common';

import {
    ApiAcceptedResponse,
    ApiCreatedResponse,
    ApiOkResponse,
    ApiOperation,
    ApiResponse,
    ApiTags,
    getSchemaPath,
} from '@nestjs/swagger';

import { RegisterUserService } from '../../../application/auth/register-user.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwAuthRegistrationHttpError } from './auth-registration-error.mapper';
import { RegisterUserDto } from './dto/register-user.dto';
import { RegisterUserResponseDto } from './dto/register-user-response.dto';

import { ConfirmEmailDto } from './dto/confirm-email.dto';
import {
    EMAIL_CONFIRMATION_MESSAGE,
    EmailConfirmationRequestResponseDto,
} from './dto/email-confirmation-request-response.dto';
import { LoginUserResponseDto } from './dto/login-user-response.dto';
import { RequestEmailConfirmationDto } from './dto/request-email-confirmation.dto';
import { throwEmailConfirmationHttpError } from './email-confirmation-error.mapper';

const problemContent = {
    'application/problem+json': {
        schema: { $ref: getSchemaPath(ProblemDetailsDto) },
    },
};

@ApiTags('Authentication')
@Controller('registrations')
export class RegistrationController {
    constructor(private readonly registerUserService: RegisterUserService) {}

    @Post()
    @HttpCode(HttpStatus.CREATED)
    @ApiOperation({
        summary: 'Register a user',
        description:
            'Creates a Supabase Auth identity using email and password.',
    })
    @ApiCreatedResponse({
        description:
            'The identity was created. Email confirmation may still be pending.',
        type: RegisterUserResponseDto,
    })
    @ApiResponse({
        status: HttpStatus.CONFLICT,
        description: 'The email is already registered.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.UNPROCESSABLE_ENTITY,
        description: 'The registration data is invalid.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.TOO_MANY_REQUESTS,
        description: 'The registration request was rate limited.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.SERVICE_UNAVAILABLE,
        description: 'Supabase Auth is temporarily unavailable.',
        type: ProblemDetailsDto,
    })
    async register(
        @Body() dto: RegisterUserDto,
    ): Promise<RegisterUserResponseDto> {
        try {
            return await this.registerUserService.execute(dto);
        } catch (error) {
            throwAuthRegistrationHttpError(error);
        }
    }

    @Post('email-confirmations')
    @Header('Cache-Control', 'no-store')
    @HttpCode(HttpStatus.OK)
    @ApiOperation({
        summary: 'Confirm a registration using an email code',
        description:
            'Verifies a six-digit signup code and returns the Supabase session. Does not require a Bearer token. The code is consumed after successful provider verification.',
    })
    @ApiOkResponse({ type: LoginUserResponseDto })
    @ApiResponse({
        status: 401,
        description: 'Invalid, expired or already used confirmation code.',
        content: problemContent,
    })
    @ApiResponse({
        status: 403,
        description: 'Email confirmation is not allowed.',
        content: problemContent,
    })
    @ApiResponse({
        status: 422,
        description: 'Invalid email, code format or unexpected fields.',
        content: problemContent,
    })
    @ApiResponse({
        status: 429,
        description: 'Too many verification attempts.',
        content: problemContent,
    })
    @ApiResponse({
        status: 503,
        description: 'Supabase Auth is unavailable or returned invalid data.',
        content: problemContent,
    })
    async confirm(@Body() dto: ConfirmEmailDto): Promise<LoginUserResponseDto> {
        try {
            return await this.registerUserService.confirm(dto);
        } catch (error) {
            throwEmailConfirmationHttpError(error);
        }
    }

    @Post('email-confirmation-requests')
    @Header('Cache-Control', 'no-store')
    @HttpCode(HttpStatus.ACCEPTED)
    @ApiOperation({
        summary: 'Request another signup confirmation code',
        description:
            'Returns a neutral result for valid input, including unknown or confirmed accounts and provider failures. Does not guarantee email delivery. Supabase enforces delivery rate limits.',
    })
    @ApiAcceptedResponse({ type: EmailConfirmationRequestResponseDto })
    @ApiResponse({
        status: 422,
        description: 'Invalid email or unexpected fields.',
        content: problemContent,
    })
    async resend(
        @Body() dto: RequestEmailConfirmationDto,
    ): Promise<EmailConfirmationRequestResponseDto> {
        await this.registerUserService.resend(dto.email);
        return { message: EMAIL_CONFIRMATION_MESSAGE };
    }
}
