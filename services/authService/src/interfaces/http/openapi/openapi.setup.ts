import { INestApplication } from '@nestjs/common';
import { DocumentBuilder, getSchemaPath, SwaggerModule, type OpenAPIObject } from '@nestjs/swagger';

import { ProblemDetailsDto } from '../common/errors/problem-details.dto';

export function createAuthOpenApiDocument(app: INestApplication): OpenAPIObject {
  const config = new DocumentBuilder()
    .setTitle('Cluster JAM Auth Service')
    .setDescription(
      'HTTP API for Cluster JAM authentication and session operations. Identity and credentials are delegated to Supabase Auth.',
    )
    .setVersion('1.0.0')
    .addTag('Health', 'Technical endpoints for service health checks.')
    .addTag('Authentication', 'Registration, login, sessions and password recovery.')
    .addBearerAuth(
      {
        type: 'http',
        scheme: 'bearer',
        bearerFormat: 'JWT',
        description: 'Supabase Auth access token.',
      },
      'supabase-jwt',
    )
    .addGlobalResponse({
      status: 'default',
      description: 'Error response using RFC 9457 Problem Details.',
      content: {
        'application/problem+json': {
          schema: {
            $ref: getSchemaPath(ProblemDetailsDto),
          },
        },
      },
    })
    .build();

  return SwaggerModule.createDocument(app, config, {
    extraModels: [ProblemDetailsDto],
  });
}

export function setupOpenApi(app: INestApplication): void {
  const document = createAuthOpenApiDocument(app);
  SwaggerModule.setup('docs', app, document, {
    jsonDocumentUrl: 'openapi.json',
  });
}
