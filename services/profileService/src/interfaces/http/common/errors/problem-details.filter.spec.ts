import { jest } from '@jest/globals';
import { HttpException, type ArgumentsHost } from '@nestjs/common';
import type { Request, Response } from 'express';
import { ProblemDetailsFilter } from './problem-details.filter';

describe('Unexpected HTTP error sanitization', () => {
    it.each([
        new Error('SQL private-password private@example.com'),
        new HttpException({ privateToken: 'secret' }, 500),
    ])('returns a generic correlated problem without serializing raw errors', (exception) => {
        const json = jest.fn();
        const type = jest.fn().mockReturnThis();
        const response = {
            status: jest.fn().mockReturnThis(),
            set: jest.fn().mockReturnThis(),
            type,
            json,
        } as unknown as Response;
        const request = { originalUrl: '/api/v1/profiles/me?token=secret' } as Request;
        const host = {
            switchToHttp: () => ({ getRequest: () => request, getResponse: () => response }),
        } as ArgumentsHost;
        new ProblemDetailsFilter().catch(exception, host);
        expect(json).toHaveBeenCalledWith({
            type: 'about:blank',
            title: 'Internal Server Error',
            status: 500,
            detail: 'An unexpected error occurred.',
            instance: '/api/v1/profiles/me',
            code: 'INTERNAL_ERROR',
            traceId: expect.stringMatching(/^[a-f0-9]{32}$/) as string,
        });
        expect(type).toHaveBeenCalledWith('application/problem+json');
        expect(JSON.stringify(json.mock.calls)).not.toMatch(/secret|private-password|SQL|private@example/);
    });
});
