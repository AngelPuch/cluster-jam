import { Injectable } from '@nestjs/common';
import { context, propagation, ROOT_CONTEXT, SpanKind, SpanStatusCode, trace } from '@opentelemetry/api';
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks';
import { W3CTraceContextPropagator } from '@opentelemetry/core';
import { TracerProvider } from '@opentelemetry/sdk-trace';

let initialized = false;

export function readLogCorrelation(): { trace_id: string | null; span_id: string | null } {
    const span = trace.getSpanContext(context.active());
    return { trace_id: span?.traceId ?? null, span_id: span?.spanId ?? null };
}

@Injectable()
export class TraceContextService {
    constructor() {
        if (!initialized) {
            context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
            propagation.setGlobalPropagator(new W3CTraceContextPropagator());
            trace.setGlobalTracerProvider(new TracerProvider({ spanProcessors: [] }));
            initialized = true;
        }
    }

    get traceId(): string {
        return trace.getSpanContext(context.active())!.traceId;
    }

    runHttp(traceparent: unknown, next: () => void): void {
        const parent = propagation.extract(ROOT_CONTEXT, {
            traceparent: typeof traceparent === 'string' && traceparent.length <= 512 ? traceparent : undefined,
        });
        const span = trace
            .getTracer('payments-service')
            .startSpan('payments HTTP request', { kind: SpanKind.SERVER }, parent);
        context.with(trace.setSpan(parent, span), next);
    }

    bindHttp(work: () => void): () => void {
        return context.bind(context.active(), work);
    }

    endHttp(status: number): void {
        const span = trace.getSpan(context.active());
        span?.setAttribute('http.response.status_code', status);
        if (status >= 500) span?.setStatus({ code: SpanStatusCode.ERROR });
        span?.end();
    }
}
