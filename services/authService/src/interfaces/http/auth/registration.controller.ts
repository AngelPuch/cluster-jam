import { Body, Controller, HttpCode, HttpStatus, Post } from '@nestjs/common';
import {
    ApiCreatedResponse,
    ApiOperation,
    ApiResponse,
    ApiTags,
} from '@nestjs/swagger';

import { RegisterUserService } from '../../../application/auth/register-user.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwAuthRegistrationHttpError } from './auth-registration-error.mapper';
import { RegisterUserDto } from './dto/register-user.dto';
import { RegisterUserResponseDto } from './dto/register-user-response.dto';

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
}
