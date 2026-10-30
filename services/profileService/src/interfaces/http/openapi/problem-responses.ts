import { ApiProperty, type ApiResponseOptions, getSchemaPath } from '@nestjs/swagger';

export class ProblemDetailsDto {
    @ApiProperty({ example: 'about:blank' }) type!: string;
    @ApiProperty({ example: 'Unprocessable Entity' }) title!: string;
    @ApiProperty({ example: 422 }) status!: number;
    @ApiProperty({ example: 'The request contains invalid or unknown fields.' }) detail!: string;
    @ApiProperty({ example: '/api/v1/profiles/me' }) instance!: string;
    @ApiProperty({ example: 'VALIDATION_ERROR' }) code!: string;
    @ApiProperty({ example: '19ef631176494c4ca0a63c428da97850', pattern: '^[a-f0-9]{32}$' }) traceId!: string;
}

const codes: Record<number, string[]> = {
    400: ['BAD_REQUEST'],
    401: ['INVALID_ACCESS_TOKEN'],
    403: ['INVALID_APP_ROLE'],
    404: ['PROFILE_NOT_READY'],
    412: ['PRECONDITION_FAILED'],
    413: ['PAYLOAD_TOO_LARGE'],
    415: ['UNSUPPORTED_MEDIA_TYPE'],
    422: ['VALIDATION_ERROR', 'PROFILE_CONTACT_EMAIL_REQUIRED'],
    428: ['PRECONDITION_REQUIRED'],
    500: ['INTERNAL_ERROR'],
    503: ['SERVICE_UNAVAILABLE'],
};
export const profileProblemResponses: Record<number, ApiResponseOptions> = Object.fromEntries(
    Object.entries(codes).map(([status, failures]) => [
        status,
        {
            status: Number(status),
            description: failures.join(' or '),
            headers: {
                'Cache-Control': { schema: { type: 'string', enum: ['no-store'] } },
                ...(status === '401' ? { 'WWW-Authenticate': { schema: { type: 'string', enum: ['Bearer'] } } } : {}),
            },
            content: {
                'application/problem+json': {
                    schema: { $ref: getSchemaPath(ProblemDetailsDto) },
                    examples: Object.fromEntries(
                        failures.map((code) => [
                            code,
                            {
                                value: {
                                    type: 'about:blank',
                                    title: 'Request failed',
                                    status: Number(status),
                                    detail: 'See the operation description for recovery.',
                                    instance: '/api/v1/profiles/me',
                                    code,
                                    traceId: '19ef631176494c4ca0a63c428da97850',
                                },
                            },
                        ]),
                    ),
                },
            },
        },
    ]),
);
