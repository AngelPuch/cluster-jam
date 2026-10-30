import {
    applyDecorators,
    Body,
    Controller,
    Delete,
    Get,
    Headers,
    HttpCode,
    Param,
    ParseUUIDPipe,
    Patch,
    Post,
    Res,
    UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiConsumes, ApiHeader, ApiOperation, ApiParam, ApiResponse, ApiTags } from '@nestjs/swagger';
import type { Response } from 'express';
import { GetMyAddressesService } from '../../../application/addresses/get-my-addresses.service';
import { ManageMyAddressesService } from '../../../application/addresses/manage-my-addresses.service';
import type { OwnerAddress } from '../../../application/addresses/address';
import type { VerifiedIdentity } from '../../../application/security/verified-identity';
import { CurrentIdentity } from '../profiles/current-identity.decorator';
import { JwtAuthGuard } from '../profiles/jwt-auth.guard';
import { requireStrongIfMatch } from '../common/conditional-request';
import { JsonContentGuard } from '../common/json-content.guard';
import { addressProblemResponses } from '../openapi/problem-responses';
import { AddressListResponseDto, AddressResponseDto, CreateAddressDto, UpdateAddressDto } from './dto/address.dto';

function ApiAddressErrors(...statuses: number[]) {
    return applyDecorators(...statuses.map((status) => ApiResponse(addressProblemResponses[status])));
}
function ApiAddressId() {
    return ApiParam({
        name: 'addressId',
        format: 'uuid',
        description: 'Owned address UUID; foreign and missing IDs both return 404 ADDRESS_NOT_FOUND.',
    });
}
function ApiIfMatch(source: string) {
    return ApiHeader({
        name: 'If-Match',
        required: true,
        description: `One strong quoted ETag from ${source}. Any address-book change invalidates earlier revisions. Missing: 428; unsupported syntax: 400; stale: 412.`,
        schema: { type: 'string', pattern: '^"[a-f0-9]{64}"$' },
    });
}
const etagHeader = {
    ETag: {
        description: 'Strong revision. See the If-Match source documented on each mutation.',
        schema: { type: 'string' },
    },
    'Cache-Control': { schema: { type: 'string', enum: ['no-store'] } },
};

@ApiTags('Addresses')
@ApiBearerAuth('supabase-jwt')
@UseGuards(JwtAuthGuard)
@Controller('profiles/me/addresses')
export class AddressesController {
    constructor(
        private readonly reads: GetMyAddressesService,
        private readonly writes: ManageMyAddressesService,
    ) {}

    @Get()
    @ApiHeader({
        name: 'If-None-Match',
        required: false,
        description: 'Matching collection ETag returns 304 after owner authentication.',
    })
    @ApiOperation({
        summary: 'List owned addresses and get the collection revision',
        description:
            'Returns an empty list for a provisioned owner with no addresses. Never creates a profile. Sorted by UUID for stable revisions. No onboarding requirement.',
    })
    @ApiResponse({ status: 200, type: AddressListResponseDto, headers: etagHeader })
    @ApiResponse({
        status: 304,
        description: 'Authenticated If-None-Match conditional read; no body.',
        headers: etagHeader,
    })
    @ApiAddressErrors(401, 403, 404, 500, 503)
    async list(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Res({ passthrough: true }) response: Response,
    ): Promise<AddressListResponseDto> {
        const book = await this.reads.list(identity.userId);
        this.setRevision(response, book.revision);
        return { items: book.items.map((address) => AddressResponseDto.from(address)) };
    }

    @Get(':addressId')
    @ApiHeader({
        name: 'If-None-Match',
        required: false,
        description: 'Matching item ETag returns 304 after owner authentication.',
    })
    @ApiOperation({
        summary: 'Read one owned address and its item revision',
        description:
            'Use this ETag for PATCH/DELETE. It also covers the whole owned address book to protect default selection. Changes to any address require refreshing it.',
    })
    @ApiAddressId()
    @ApiResponse({ status: 200, type: AddressResponseDto, headers: etagHeader })
    @ApiResponse({
        status: 304,
        description: 'Authenticated If-None-Match conditional read; no body.',
        headers: etagHeader,
    })
    @ApiAddressErrors(400, 401, 403, 404, 500, 503)
    async get(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Param('addressId', new ParseUUIDPipe()) addressId: string,
        @Res({ passthrough: true }) response: Response,
    ): Promise<AddressResponseDto> {
        return this.respond(response, await this.reads.get(identity.userId, addressId));
    }

    @Post()
    @UseGuards(JsonContentGuard)
    @ApiConsumes('application/json')
    @ApiOperation({
        summary: 'Create an owned address',
        description:
            'Ownership comes only from JWT sub. isDefault defaults to false; true explicitly replaces the previous default atomically. Creating an address does not complete onboarding.',
    })
    @ApiIfMatch('GET /api/v1/profiles/me/addresses (collection)')
    @ApiResponse({
        status: 201,
        type: AddressResponseDto,
        headers: {
            ...etagHeader,
            Location: { description: 'Canonical URL of the created owned address.', schema: { type: 'string' } },
        },
    })
    @ApiAddressErrors(400, 401, 403, 404, 412, 413, 415, 422, 428, 500, 503)
    async create(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Body() input: CreateAddressDto,
        @Headers('if-match') etag: string | undefined,
        @Res({ passthrough: true }) response: Response,
    ): Promise<AddressResponseDto> {
        const address = await this.writes.create(identity.userId, input, requireStrongIfMatch(etag));
        response.setHeader('Location', '/api/v1/profiles/me/addresses/' + address.id);
        return this.respond(response, address);
    }

    @Patch(':addressId')
    @UseGuards(JsonContentGuard)
    @ApiConsumes('application/json')
    @ApiOperation({
        summary: 'Partially edit an owned address or select its default state',
        description:
            'Omitted fields are preserved. Only interiorNumber accepts null to clear it. At least one allowed field is required. isDefault=true replaces the previous default; false can leave no default.',
    })
    @ApiAddressId()
    @ApiIfMatch('GET of this address or its most recent POST/PATCH response (item)')
    @ApiResponse({ status: 200, type: AddressResponseDto, headers: etagHeader })
    @ApiAddressErrors(400, 401, 403, 404, 412, 413, 415, 422, 428, 500, 503)
    async update(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Param('addressId', new ParseUUIDPipe()) addressId: string,
        @Body() input: UpdateAddressDto,
        @Headers('if-match') etag: string | undefined,
        @Res({ passthrough: true }) response: Response,
    ): Promise<AddressResponseDto> {
        return this.respond(
            response,
            await this.writes.update(identity.userId, addressId, input, requireStrongIfMatch(etag)),
        );
    }

    @Delete(':addressId')
    @HttpCode(204)
    @ApiOperation({
        summary: 'Delete an owned address',
        description:
            'Deletes this Profile address only. Deleting the default leaves no default and does not rewrite any Orders snapshot. No replacement is selected automatically.',
    })
    @ApiAddressId()
    @ApiIfMatch('GET of this address or its most recent POST/PATCH response (item)')
    @ApiResponse({ status: 204, description: 'Deleted after commit; no response body.' })
    @ApiAddressErrors(400, 401, 403, 404, 412, 428, 500, 503)
    async delete(
        @CurrentIdentity() identity: VerifiedIdentity,
        @Param('addressId', new ParseUUIDPipe()) addressId: string,
        @Headers('if-match') etag: string | undefined,
        @Res({ passthrough: true }) response: Response,
    ): Promise<void> {
        await this.writes.delete(identity.userId, addressId, requireStrongIfMatch(etag));
        response.setHeader('Cache-Control', 'no-store');
    }

    private setRevision(response: Response, revision: string): void {
        response.setHeader('ETag', '"' + revision + '"');
        response.setHeader('Cache-Control', 'no-store');
    }
    private respond(response: Response, address: OwnerAddress): AddressResponseDto {
        this.setRevision(response, address.revision);
        return AddressResponseDto.from(address);
    }
}
