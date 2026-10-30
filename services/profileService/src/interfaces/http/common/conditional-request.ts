import { BadRequestException, HttpException, UnsupportedMediaTypeException } from '@nestjs/common';

export function requireStrongIfMatch(etag: string | undefined): string {
    if (!etag) throw new HttpException({ code: 'PRECONDITION_REQUIRED' }, 428);
    const revision = /^"([a-f0-9]{64})"$/.exec(etag)?.[1];
    if (!revision) throw new BadRequestException();
    return revision;
}
export function requireJson(contentType: string | undefined): void {
    if (contentType?.split(';')[0].trim().toLowerCase() !== 'application/json')
        throw new UnsupportedMediaTypeException();
}
