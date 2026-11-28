import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { randomUUID } from 'node:crypto';
import Stripe from 'stripe';

// Local HTTP fixture exercises the real SDK without contacting Stripe.
export class StripeFixture {
    readonly requests: Array<{ key: string; form: URLSearchParams }> = [];
    readonly intents = new Map<string, Record<string, unknown>>();
    dropCreateResponses = 0;
    responseOverride: Record<string, unknown> = {};
    private readonly server = createServer((request, response) => {
        void this.handle(request, response).catch(() => {
            response.writeHead(500).end();
        });
    });

    async open(): Promise<Stripe> {
        await new Promise<void>((resolve) => this.server.listen(0, '127.0.0.1', resolve));
        const address = this.server.address();
        if (!address || typeof address === 'string') throw new Error('Fixture did not bind a TCP port.');
        return new Stripe('sk_test_localFixtureOnly', {
            apiVersion: '2026-11-18.endive',
            host: '127.0.0.1',
            port: address.port,
            protocol: 'http',
            maxNetworkRetries: 0,
            timeout: 2000,
            telemetry: false,
        });
    }

    async close(): Promise<void> {
        await new Promise<void>((resolve, reject) => {
            this.server.close((error) => (error ? reject(error) : resolve()));
            this.server.closeAllConnections();
        });
    }

    private async handle(request: IncomingMessage, response: ServerResponse): Promise<void> {
        let intent: Record<string, unknown> | undefined;
        if (request.method === 'POST' && request.url === '/v1/payment_intents') {
            const chunks: Buffer[] = [];
            for await (const chunk of request) chunks.push(Buffer.from(chunk as Uint8Array));
            const form = new URLSearchParams(Buffer.concat(chunks).toString());
            const key = String(request.headers['idempotency-key'] ?? '');
            this.requests.push({ key, form });
            intent = this.intents.get(key);
            if (!intent) {
                intent = {
                    id: 'pi_fixture' + randomUUID().replaceAll('-', ''),
                    object: 'payment_intent',
                    livemode: false,
                    amount: Number(form.get('amount')),
                    currency: form.get('currency'),
                    status: 'requires_payment_method',
                    client_secret: 'pi_fixture_secret_local_only',
                    metadata: Object.fromEntries(
                        [...form.entries()]
                            .filter(([name]) => name.startsWith('metadata['))
                            .map(([name, value]) => [name.slice(9, -1), value]),
                    ),
                };
                this.intents.set(key, intent);
            }
            if (this.dropCreateResponses > 0) {
                this.dropCreateResponses--;
                response.destroy();
                return;
            }
        } else if (request.method === 'GET') {
            intent = [...this.intents.values()].find(
                (value) => request.url === '/v1/payment_intents/' + String(value.id),
            );
        }
        if (!intent) {
            response.writeHead(404).end();
            return;
        }
        response.writeHead(200, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ ...intent, ...this.responseOverride }));
    }
}
