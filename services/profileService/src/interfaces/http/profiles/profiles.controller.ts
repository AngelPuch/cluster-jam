import { Body, Controller, Get, Headers, Patch, Res, UseGuards } from '@nestjs/common';
import type { Response } from 'express';
import { ApiBearerAuth, ApiConsumes, ApiHeader, ApiOperation, ApiResponse, ApiTags } from '@nestjs/swagger';
import { GetMyProfileService } from '../../../application/profile/get-my-profile.service';
import { CompleteOnboardingService } from '../../../application/profile/complete-onboarding.service';
import type { VerifiedIdentity } from '../../../application/security/verified-identity';
import type { CustomerProfile } from '../../../application/profile/profile';
import { CurrentIdentity } from './current-identity.decorator';
import { JwtAuthGuard } from './jwt-auth.guard';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { ProfileResponseDto } from './dto/profile-response.dto';
import { profileProblemResponses } from '../openapi/problem-responses';
import { requireStrongIfMatch } from '../common/conditional-request';
import { JsonContentGuard } from '../common/json-content.guard';

@ApiTags('Profiles')
@ApiBearerAuth('supabase-jwt')
@UseGuards(JwtAuthGuard)
@Controller('profiles')
export class ProfilesController {
    constructor(
        private readonly getProfile: GetMyProfileService,
        private readonly updateProfile: CompleteOnboardingService,
    ) {}

    @Get('me')
    @ApiHeader({
        name: 'If-None-Match',
        required: false,
        description: 'Optional HTTP conditional read. Matching revisions return 304 after authentication.',
    })
    @ApiOperation({
        summary: 'Read the authenticated owner profile',
        description:
            'Identity comes only from the verified JWT sub. A profile awaiting the registration event returns 404 PROFILE_NOT_READY; GET never creates it.',
    })
    @ApiResponse({
        status: 200,
        type: ProfileResponseDto,
        description: 'Owner profile and onboarding state.',
        headers: {
            ETag: { description: 'Strong revision required in If-Match when updating.', schema: { type: 'string' } },
        },
    })
    @ApiResponse(profileProblemResponses[401])
    @ApiResponse({
        status: 304,
        description: 'Authenticated conditional read; no response body.',
        headers: {
            ETag: { schema: { type: 'string' } },
            'Cache-Control': { schema: { type: 'string', enum: ['no-store'] } },
        },
    })
    @ApiResponse(profileProblemResponses[403])
    @ApiResponse(profileProblemResponses[404])
    @ApiResponse(profileProblemResponses[503])
    @ApiResponse(profileProblemResponses[500])
    async getMine(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Res({ passthrough: true }) response: Response,
    ): Promise<ProfileResponseDto> {
        return this.respond(response, await this.getProfile.execute(identity.userId));
    }

    @Patch('me')
    @UseGuards(JsonContentGuard)
    @ApiConsumes('application/json')
    @ApiOperation({
        summary: 'Partially update the owner profile and complete onboarding',
        description:
            'At least one allowed field is required. Omitted fields are preserved; null/empty fields and unknown properties are rejected. The service derives COMPLETED only when name, phone and contact email are valid. Address is not required.',
    })
    @ApiHeader({
        name: 'If-Match',
        required: true,
        description: 'One strong quoted ETag from GET/PATCH. Wildcards, weak tags and lists are unsupported.',
        schema: { type: 'string', pattern: '^"[a-f0-9]{64}"$' },
    })
    @ApiResponse({
        status: 200,
        type: ProfileResponseDto,
        description: 'Updated profile after its transaction commits.',
        headers: { ETag: { description: 'Current strong revision.', schema: { type: 'string' } } },
    })
    @ApiResponse(profileProblemResponses[400])
    @ApiResponse(profileProblemResponses[401])
    @ApiResponse(profileProblemResponses[403])
    @ApiResponse(profileProblemResponses[404])
    @ApiResponse(profileProblemResponses[412])
    @ApiResponse(profileProblemResponses[415])
    @ApiResponse(profileProblemResponses[413])
    @ApiResponse(profileProblemResponses[422])
    @ApiResponse(profileProblemResponses[428])
    @ApiResponse(profileProblemResponses[503])
    @ApiResponse(profileProblemResponses[500])
    async patchMine(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Body() input: UpdateProfileDto,
        @Headers('if-match') etag: string | undefined,
        @Res({ passthrough: true }) response: Response,
    ): Promise<ProfileResponseDto> {
        return this.respond(
            response,
            await this.updateProfile.execute(identity.userId, input, requireStrongIfMatch(etag)),
        );
    }

    private respond(response: Response, profile: CustomerProfile): ProfileResponseDto {
        response.setHeader('ETag', '"' + profile.revision + '"');
        response.setHeader('Cache-Control', 'no-store');
        return ProfileResponseDto.from(profile);
    }
}
