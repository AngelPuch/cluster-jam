import { Body, Controller, HttpCode, HttpStatus, Post } from '@nestjs/common';
import {
    ApiOkResponse,
    ApiOperation,
    ApiResponse,
    ApiTags,
} from '@nestjs/swagger';

import { LoginUserService } from '../../../application/auth/login-user.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwAuthLoginHttpError } from './auth-login-error.mapper';
import { LoginUserDto } from './dto/login-user.dto';
import { LoginUserResponseDto } from './dto/login-user-response.dto';

@ApiTags('Authentication')
@Controller('sessions')
export class SessionController {
    constructor(private readonly loginUserService: LoginUserService) {}

    @Post()
    @HttpCode(HttpStatus.OK)
    @ApiOperation({
        summary: 'Login a user',
        description:
            'Authenticates an existing user with email and password using Supabase Auth.',
    })
    @ApiOkResponse({
        description: 'Authentication succeeded and a session was created.',
        type: LoginUserResponseDto,
    })
    @ApiResponse({
        status: HttpStatus.UNAUTHORIZED,
        description: 'The credentials are invalid.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.FORBIDDEN,
        description: 'The email address has not been confirmed.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.UNPROCESSABLE_ENTITY,
        description: 'The login data is invalid.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.TOO_MANY_REQUESTS,
        description: 'The login request was rate limited.',
        type: ProblemDetailsDto,
    })
    @ApiResponse({
        status: HttpStatus.SERVICE_UNAVAILABLE,
        description: 'Supabase Auth is temporarily unavailable.',
        type: ProblemDetailsDto,
    })
    async login(@Body() dto: LoginUserDto): Promise<LoginUserResponseDto> {
        try {
            return await this.loginUserService.execute(dto);
        } catch (error) {
            throwAuthLoginHttpError(error);
        }
    }
}
