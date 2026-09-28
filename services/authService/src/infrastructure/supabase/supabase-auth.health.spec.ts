import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    jest,
} from '@jest/globals';

import { configService } from '../../../test/helpers/supabase-auth.fixtures';
import { SupabaseAuthAdapter } from './supabase-auth.adapter';

describe('SupabaseAuthAdapter.isAvailable', () => {
    let fetchSpy: jest.SpiedFunction<typeof fetch>;

    beforeEach(() => {
        jest.clearAllMocks();
        fetchSpy = jest.spyOn(globalThis, 'fetch');
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    it('should report Supabase Auth as available', async () => {
        fetchSpy.mockResolvedValue(
            new Response(null, {
                status: 200,
            }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(adapter.isAvailable()).resolves.toBe(true);

        expect(fetchSpy).toHaveBeenCalledWith(
            'https://test-project.supabase.co/auth/v1/health',
            expect.objectContaining({
                method: 'GET',
                headers: {
                    apikey: 'test-publishable-key',
                },
                signal: expect.any(AbortSignal) as unknown,
            }),
        );
    });

    it('should report Supabase Auth as unavailable for non-success responses', async () => {
        fetchSpy.mockResolvedValue(
            new Response(null, {
                status: 503,
            }),
        );

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(adapter.isAvailable()).resolves.toBe(false);
    });

    it('should report Supabase Auth as unavailable for network errors', async () => {
        fetchSpy.mockRejectedValue(new TypeError('Network error'));

        const adapter = new SupabaseAuthAdapter(configService);

        await expect(adapter.isAvailable()).resolves.toBe(false);
    });
});
