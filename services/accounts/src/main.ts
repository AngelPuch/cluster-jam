import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
    const app = await NestFactory.create(AppModule);

    const port = process.env.HTTP_PORT ?? 8080;

    await app.listen(port);
}

bootstrap();
