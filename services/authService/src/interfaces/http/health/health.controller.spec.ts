import { ServiceUnavailableException } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';

import { ReadinessService } from '../../../application/health/readiness.service';
import { HealthController } from './health.controller';
import { beforeEach, describe, expect, it, jest } from '@jest/globals';

describe('HealthController', () => {
    let controller: HealthController;
    let readinessService: {
        isReady: jest.Mock<() => Promise<boolean>>;
    };

    beforeEach(async () => {
        readinessService = {
            isReady: jest.fn<() => Promise<boolean>>(),
        };

        const module: TestingModule = await Test.createTestingModule({
            controllers: [HealthController],
            providers: [
                {
                    provide: ReadinessService,
                    useValue: readinessService,
                },
            ],
        }).compile();

        controller = module.get<HealthController>(HealthController);
    });

    it('should return ok for liveness', () => {
        expect(controller.getLiveness()).toEqual({
            status: 'ok',
        });
    });

    it('should return ok for readiness when dependencies are available', async () => {
        readinessService.isReady.mockResolvedValue(true);

        await expect(controller.getReadiness()).resolves.toEqual({
            status: 'ok',
        });
    });

    it('should throw service unavailable when dependencies are unavailable', async () => {
        readinessService.isReady.mockResolvedValue(false);

        await expect(controller.getReadiness()).rejects.toBeInstanceOf(
            ServiceUnavailableException,
        );
    });
});
