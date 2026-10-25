import { Body, Controller, Header, HttpCode, HttpStatus, Post } from '@nestjs/common';
import { ApiOkResponse, ApiOperation, ApiResponse, ApiTags, getSchemaPath } from '@nestjs/swagger';

import { LoginUserService } from '../../../application/auth/login-user.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwAuthLoginHttpError } from './auth-login-error.mapper';
import { LoginUserDto } from './dto/login-user.dto';
import { LoginUserResponseDto } from './dto/login-user-response.dto';

const problemContent = {
  'application/problem+json': {
    schema: { $ref: getSchemaPath(ProblemDetailsDto) },
  },
};

@ApiTags('Authentication')
@Controller('sessions')
export class SessionController {
  constructor(private readonly loginUserService: LoginUserService) {}

  @Post()
  @Header('Cache-Control', 'no-store')
  @HttpCode(HttpStatus.OK)
  @ApiOperation({
    summary: 'Login a user',
    description: 'Authenticates an existing user with email and password using Supabase Auth.',
  })
  @ApiOkResponse({
    description: 'Authentication succeeded and a session was created.',
    type: LoginUserResponseDto,
  })
  @ApiResponse({
    status: HttpStatus.UNAUTHORIZED,
    description: 'The credentials are invalid.',
    content: problemContent,
  })
  @ApiResponse({
    status: HttpStatus.FORBIDDEN,
    description: 'The email address has not been confirmed.',
    content: problemContent,
  })
  @ApiResponse({
    status: HttpStatus.UNPROCESSABLE_ENTITY,
    description: 'The login data is invalid.',
    content: problemContent,
  })
  @ApiResponse({
    status: HttpStatus.TOO_MANY_REQUESTS,
    description: 'The login request was rate limited.',
    content: problemContent,
  })
  @ApiResponse({
    status: HttpStatus.SERVICE_UNAVAILABLE,
    description: 'Supabase Auth is temporarily unavailable.',
    content: problemContent,
  })
  async login(@Body() dto: LoginUserDto): Promise<LoginUserResponseDto> {
    try {
      return await this.loginUserService.execute(dto);
    } catch (error) {
      throwAuthLoginHttpError(error);
    }
  }
}
