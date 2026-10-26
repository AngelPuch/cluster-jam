import { Injectable } from '@nestjs/common';
import {
  context,
  createContextKey,
  propagation,
  ROOT_CONTEXT,
  SpanKind,
  SpanStatusCode,
  trace,
  type Context,
  type Span,
} from '@opentelemetry/api';
import { AsyncLocalStorageContextManager } from '@opentelemetry/context-async-hooks';
import { W3CTraceContextPropagator } from '@opentelemetry/core';
import { TracerProvider } from '@opentelemetry/sdk-trace';

import type { TraceContextPort } from '../../application/ports/trace-context.port';

const REQUEST_ID_KEY = createContextKey('auth.request_id');
let initialized = false;

function initializeTracing(): void {
  if (initialized) return;
  context.setGlobalContextManager(new AsyncLocalStorageContextManager().enable());
  propagation.setGlobalPropagator(new W3CTraceContextPropagator());
  trace.setGlobalTracerProvider(new TracerProvider({ spanProcessors: [] }));
  initialized = true;
}

export function readLogCorrelation(): {
  trace_id: string | null;
  span_id: string | null;
  request_id?: string;
} {
  const activeContext = context.active();
  const spanContext = trace.getSpanContext(activeContext);
  const requestId = activeContext.getValue(REQUEST_ID_KEY);
  return {
    trace_id: spanContext?.traceId ?? null,
    span_id: spanContext?.spanId ?? null,
    ...(typeof requestId === 'string' ? { request_id: requestId } : {}),
  };
}

@Injectable()
export class TraceContextService implements TraceContextPort {
  constructor() {
    initializeTracing();
  }

  startHttp(traceparent: string | undefined, requestId: string): { span: Span; scope: Context } {
    const parent = propagation.extract(ROOT_CONTEXT, { traceparent });
    const span = trace.getTracer('auth-service').startSpan(
      'HTTP request',
      {
        kind: SpanKind.SERVER,
      },
      parent,
    );
    return {
      span,
      scope: trace.setSpan(parent, span).setValue(REQUEST_ID_KEY, requestId),
    };
  }

  runJob<T>(work: () => Promise<T>): Promise<T> {
    return this.runSpan('auth.outbox.batch', SpanKind.INTERNAL, ROOT_CONTEXT, work);
  }

  runProducer<T>(work: (traceparent: string) => Promise<T>): Promise<T> {
    return this.runSpan(
      'identity.user.registered.v1 publish',
      SpanKind.PRODUCER,
      context.active(),
      () => {
        const carrier: Record<string, string> = {};
        propagation.inject(context.active(), carrier);
        return work(carrier.traceparent);
      },
    );
  }

  private async runSpan<T>(
    name: string,
    kind: SpanKind,
    parent: Context,
    work: () => Promise<T>,
  ): Promise<T> {
    const span = trace.getTracer('auth-service').startSpan(name, { kind }, parent);
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
