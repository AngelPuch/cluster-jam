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

    runConsumer<T>(traceparent: unknown, work: () => Promise<T>): Promise<T> {
        const parent = propagation.extract(ROOT_CONTEXT, {
            traceparent: typeof traceparent === 'string' && traceparent.length <= 512 ? traceparent : undefined,
        });
        return this.runMessaging(SpanKind.CONSUMER, parent, work);
    }

    runProducer<T>(work: () => Promise<T>): Promise<T> {
        return this.runMessaging(SpanKind.PRODUCER, context.active(), work);
    }

    inject(): Record<string, string> {
        const headers: Record<string, string> = {};
        propagation.inject(context.active(), headers);
        return headers;
    }

    private async runMessaging<T>(
        kind: SpanKind,
        parent: ReturnType<typeof context.active>,
        work: () => Promise<T>,
    ): Promise<T> {
        const span = trace.getTracer('payments-service').startSpan('payments AMQP', { kind }, parent);
        try {
            return await context.with(trace.setSpan(parent, span), work);
        } catch (error) {
            span.setStatus({ code: SpanStatusCode.ERROR });
            throw error;
        } finally {
            span.end();
        }
    }
}
