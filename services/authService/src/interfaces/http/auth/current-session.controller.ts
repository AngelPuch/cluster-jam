import { Controller, Delete, Get, Header, Headers, HttpCode, HttpStatus } from '@nestjs/common';
import {
  ApiBearerAuth,
  ApiNoContentResponse,
  ApiOkResponse,
  ApiOperation,
  ApiResponse,
  ApiTags,
  getSchemaPath,
} from '@nestjs/swagger';

import { CurrentSessionService } from '../../../application/auth/current-session.service';
import { ProblemDetailsDto } from '../common/errors/problem-details.dto';
import { throwCurrentSessionHttpError } from './current-session-error.mapper';
import { CurrentIdentityResponseDto } from './dto/current-identity-response.dto';
import { readBearerToken } from './read-bearer-token';

const problemContent = {
  'application/problem+json': {
    schema: { $ref: getSchemaPath(ProblemDetailsDto) },
  },
};

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
      'Checks the current Supabase session and returns its user ID, email and current application role.',
  })
  @ApiOkResponse({ type: CurrentIdentityResponseDto })
  @ApiResponse({ status: 401, content: problemContent })
  @ApiResponse({
    status: 403,
    description: 'Missing or invalid application role.',
    content: problemContent,
  })
  @ApiResponse({ status: 429, content: problemContent })
  @ApiResponse({ status: 503, content: problemContent })
  async getIdentity(
    @Headers('authorization') authorization?: string,
  ): Promise<CurrentIdentityResponseDto> {
    try {
      return await this.sessions.getIdentity(readBearerToken(authorization));
    } catch (error) {
      throwCurrentSessionHttpError(error);
    }
  }

  @Delete()
  @HttpCode(HttpStatus.NO_CONTENT)
  @Header('Cache-Control', 'no-store')
  @ApiOperation({
    summary: 'End the current session',
    description: 'Revokes only this Supabase session. The client must discard its tokens.',
  })
  @ApiNoContentResponse({ description: 'The current session was ended.' })
  @ApiResponse({ status: 401, content: problemContent })
  @ApiResponse({ status: 429, content: problemContent })
  @ApiResponse({ status: 503, content: problemContent })
  async end(@Headers('authorization') authorization?: string): Promise<void> {
    try {
      await this.sessions.end(readBearerToken(authorization));
    } catch (error) {
      throwCurrentSessionHttpError(error);
    }
  }
}
