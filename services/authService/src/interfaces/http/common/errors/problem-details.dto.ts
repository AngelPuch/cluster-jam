import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class ProblemDetailsDto {
    @ApiProperty({
        example: 'about:blank',
    })
    type!: string;

    @ApiProperty({
        example: 'Not Found',
    })
    title!: string;

    @ApiProperty({
        example: 404,
    })
    status!: number;

    @ApiProperty({
        example: 'Cannot GET /missing',
    })
    detail!: string;

    @ApiProperty({
        example: '/missing',
    })
    instance!: string;

    @ApiProperty({
        example: 'NOT_FOUND',
    })
    code!: string;

    @ApiPropertyOptional({
        type: [String],
        example: ['email must be an email'],
    })
    errors?: string[];

    @ApiPropertyOptional({
        example: '4bf92f3577b34da6a3ce929d0e0e4736',
    })
    traceId?: string;
}
