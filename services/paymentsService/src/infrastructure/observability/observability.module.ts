import { Global, Module } from '@nestjs/common';
import { JsonLogger } from './json-logger.service';
import { TraceContextService } from './trace-context.service';

@Global()
@Module({ providers: [JsonLogger, TraceContextService], exports: [JsonLogger, TraceContextService] })
export class ObservabilityModule {}
