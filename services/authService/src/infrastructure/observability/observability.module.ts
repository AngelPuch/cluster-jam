import { Global, Module } from '@nestjs/common';

import { TRACE_CONTEXT_PORT } from '../../application/ports/trace-context.port';
import { JsonLogger } from './json-logger.service';
import { TraceContextService } from './trace-context.service';

@Global()
@Module({
  providers: [
    JsonLogger,
    TraceContextService,
    { provide: TRACE_CONTEXT_PORT, useExisting: TraceContextService },
  ],
  exports: [JsonLogger, TraceContextService, TRACE_CONTEXT_PORT],
})
export class ObservabilityModule {}
