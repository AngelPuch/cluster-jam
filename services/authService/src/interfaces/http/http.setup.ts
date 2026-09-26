import { HttpStatus, INestApplication, ValidationPipe } from '@nestjs/common';
import helmet from 'helmet';

import { setupOpenApi } from './openapi/openapi.setup';

export function configureHttpApplication(app: INestApplication): void {
    app.use(helmet());

    app.useGlobalPipes(
        new ValidationPipe({
            whitelist: true,
            forbidNonWhitelisted: true,
            transform: true,
            errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY,
        }),
    );

    app.setGlobalPrefix('api/v1', {
        exclude: ['health/live', 'health/ready'],
    });

    setupOpenApi(app);
}
