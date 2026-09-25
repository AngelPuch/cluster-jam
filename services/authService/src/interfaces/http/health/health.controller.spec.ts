import { Test, TestingModule } from '@nestjs/testing';

import { HealthController } from './health.controller';

describe('HealthController', () => {
    let controller: HealthController;

    beforeEach(async () => {
        const module: TestingModule = await Test.createTestingModule({
            controllers: [HealthController],
        }).compile();

        controller = module.get<HealthController>(HealthController);
    });

    it('should return ok for liveness', () => {
        expect(controller.getLiveness()).toEqual({
            status: 'ok',
        });
    });

    it('should return ok for readiness', () => {
        expect(controller.getReadiness()).toEqual({
            status: 'ok',
        });
    });
});
