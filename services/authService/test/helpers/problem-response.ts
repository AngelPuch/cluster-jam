export interface ProblemResponse {
    type: string;
    title: string;
    status: number;
    detail: string;
    instance: string;
    code: string;
    errors?: string[];
    traceId?: string;
}
