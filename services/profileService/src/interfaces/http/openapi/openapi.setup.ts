import type { INestApplication } from '@nestjs/common';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { ProblemDetailsDto } from './problem-responses';

export function configureApiPrefix(app: INestApplication): void {
    app.setGlobalPrefix('api/v1', { exclude: ['health/live', 'health/ready'] });
}

export function createProfileOpenApiDocument(app: INestApplication) {
    const config = new DocumentBuilder()
        .setTitle('Cluster JAM Profile Service')
        .setDescription(
            'Owner profile, onboarding and owned addresses. Identity is verified locally with Supabase JWKS; contact email is independent from login email. Addresses are separate from pickup onboarding. Internal Orders operations are not implemented yet.',
        )
        .setVersion('1.0.0')
        .addBearerAuth(
            {
                type: 'http',
                scheme: 'bearer',
                bearerFormat: 'JWT',
                description: 'Supabase authenticated user JWT with trusted app_metadata.app_role.',
            },
            'supabase-jwt',
        )
        .build();
    const document = SwaggerModule.createDocument(app, config, { extraModels: [ProblemDetailsDto] });
    // A partial update must contain at least one allowed property; Nest validation enforces this too.
    const update = document.components?.schemas?.UpdateProfileDto;
    if (update && !('$ref' in update)) {
        update.minProperties = 1;
        update.additionalProperties = false;
    }
    for (const name of ['CreateAddressDto', 'UpdateAddressDto']) {
        const schema = document.components?.schemas?.[name];
        if (schema && !('$ref' in schema)) {
            schema.additionalProperties = false;
            if (name === 'UpdateAddressDto') schema.minProperties = 1;
        }
    }
    return document;
}

export function setupOpenApi(app: INestApplication): void {
    SwaggerModule.setup('docs', app, createProfileOpenApiDocument(app), {
        jsonDocumentUrl: '/openapi.json',
        swaggerOptions: { persistAuthorization: false },
    });
}
