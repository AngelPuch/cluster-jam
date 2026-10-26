export const TRACE_CONTEXT_PORT = Symbol('TRACE_CONTEXT_PORT');

export interface TraceContextPort {
  runJob<T>(work: () => Promise<T>): Promise<T>;
  runProducer<T>(work: (traceparent: string) => Promise<T>): Promise<T>;
}
