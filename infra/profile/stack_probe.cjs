const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { randomUUID } = require('node:crypto');
const { request: httpsRequest } = require('node:https');
const amqp = require(require.resolve('amqplib', { paths: ['/app'] }));
const origin = 'https://clusterjam.test:8443';
const first = '11111111-1111-4111-8111-111111111111';
const second = '22222222-2222-4222-8222-222222222222';
const checks = [];
let operation = 'initialization';
function passed(name) {
    checks.push(name);
}
async function http(path, expected, options = {}) {
    operation = (options.method || 'GET') + ' ' + path.replace(/[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}/g, ':id');
    const response = await fetch(origin + path, { ...options, signal: AbortSignal.timeout(10000) });
    assert.equal(response.status, expected, 'Unexpected HTTP status for ' + path);
    const text = await response.text();
    return { response, body: text ? JSON.parse(text) : null };
}
async function token(sub) {
    const response = await fetch('https://profile-jwks:8443/_fixture/token?sub=' + sub, {
        signal: AbortSignal.timeout(5000),
    });
    assert.equal(response.status, 200);
    return (await response.json()).token;
}
async function publish(userId, eventId = randomUUID(), email = 'stack-initial@example.test') {
    const uri = readFileSync('/fixture/publisher-uri', 'utf8').trim();
    const connection = await amqp.connect(uri, {
        ca: [readFileSync('/fixture/ca.crt')],
        rejectUnauthorized: true,
        timeout: 5000,
    });
    try {
        const channel = await connection.createConfirmChannel();
        let returned = false;
        channel.on('return', () => {
            returned = true;
        });
        const event = {
            eventId,
            eventType: 'identity.user.registered',
            schemaVersion: 1,
            aggregateId: userId,
            aggregateVersion: 1,
            occurredAt: new Date().toISOString(),
            data: { userId, initialContactEmail: email },
        };
        channel.publish('identity.events', 'identity.user.registered.v1', Buffer.from(JSON.stringify(event)), {
            persistent: true,
            mandatory: true,
            contentType: 'application/json',
            messageId: eventId,
            type: event.eventType,
            headers: { schemaVersion: 1, traceparent: '00-11111111111111111111111111111111-2222222222222222-01' },
        });
        await channel.waitForConfirms();
        assert.equal(returned, false);
        await channel.close();
    } finally {
        await connection.close();
    }
    return eventId;
}
async function waitProfile(headers) {
    for (let attempt = 0; attempt < 50; attempt++) {
        const response = await fetch(origin + '/api/v1/profiles/me', { headers, signal: AbortSignal.timeout(5000) });
        if (response.status === 200) return { response, body: await response.json() };
        assert.equal(response.status, 404);
        await new Promise((resolve) => setTimeout(resolve, 200));
    }
    throw new Error('Profile provisioning timeout');
}
async function main() {
    const mode = process.argv[2] || 'flow';
    await http('/health/profile/live', 200);
    if (mode === 'down') {
        await http('/health/profile/ready', 503);
        passed('dependency-outage-preserves-liveness');
    } else {
        await http('/health/profile/ready', 200);
        passed('https-readiness');
        if (mode === 'persisted') {
            const auth = { Authorization: 'Bearer ' + (await token(first)) };
            const profile = await http('/api/v1/profiles/me', 200, { headers: auth });
            assert.equal(profile.body.onboardingStatus, 'COMPLETED');
            const addresses = await http('/api/v1/profiles/me/addresses', 200, { headers: auth });
            assert.equal(addresses.body.items.length, 1);
            assert.equal(addresses.body.items[0].isDefault, false);
            passed('profile-address-volume-persistence');
        } else {
            const noToken = await http('/api/v1/profiles/me', 401, {
                headers: { traceparent: '00-' + '3'.repeat(32) + '-' + '4'.repeat(16) + '-01' },
            });
            assert.equal(noToken.body.code, 'INVALID_ACCESS_TOKEN');
            assert.equal(noToken.response.headers.get('www-authenticate'), 'Bearer');
            assert.equal(noToken.body.traceId, '3'.repeat(32));
            const schema = await http('/openapi/profile.json', 200);
            assert(schema.body.paths['/api/v1/profiles/me/addresses/{addressId}']);
            const docs = await fetch(origin + '/docs/profile/');
            assert.equal(docs.status, 200);
            const html = await docs.text();
            assert(html.includes('Swagger UI'));
            for (const match of html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)) {
                const asset = new URL(match[1], docs.url);
                assert.equal(asset.origin, origin);
                assert.equal((await fetch(asset)).status, 200);
            }
            assert.equal((await fetch(origin + '/docs/profile/swagger-ui-bundle.js')).status, 200);
            passed('gateway-auth-swagger-and-assets');
            const auth = { Authorization: 'Bearer ' + (await token(first)) };
            const otherAuth = { Authorization: 'Bearer ' + (await token(second)) };
            const eventId = await publish(first);
            await publish(first, eventId);
            await publish(second);
            const pending = await waitProfile(auth);
            await waitProfile(otherAuth);
            assert.equal(pending.body.onboardingStatus, 'PENDING');
            assert.equal(pending.body.fullName, null);
            const complete = await http('/api/v1/profiles/me', 200, {
                method: 'PATCH',
                headers: {
                    ...auth,
                    'Content-Type': 'application/json',
                    'If-Match': pending.response.headers.get('etag'),
                },
                body: JSON.stringify({
                    fullName: 'Stack Customer',
                    phone: '5551234567',
                    contactEmail: 'stack-contact@example.test',
                }),
            });
            assert.equal(complete.body.onboardingStatus, 'COMPLETED');
            await publish(first, randomUUID(), 'old-login@example.test');
            passed('tls-registration-inbox-and-onboarding');
            const listPath = '/api/v1/profiles/me/addresses';
            const empty = await http(listPath, 200, { headers: auth });
            assert.deepEqual(empty.body, { items: [] });
            const addressInput = {
                label: 'Stack home',
                recipient: 'Stack Customer',
                street: 'Test street',
                exteriorNumber: '123',
                neighborhood: 'Centro',
                municipality: 'Test city',
                state: 'Test state',
                postalCode: '06000',
                country: 'MX',
                isDefault: true,
            };
            const created = await http(listPath, 201, {
                method: 'POST',
                headers: {
                    ...auth,
                    'Content-Type': 'application/json',
                    'If-Match': empty.response.headers.get('etag'),
                },
                body: JSON.stringify(addressInput),
            });
            assert.equal(created.response.headers.get('location'), listPath + '/' + created.body.id);
            const itemPath = created.response.headers.get('location');
            await http(itemPath, 404, { headers: otherAuth });
            await http(itemPath, 404, {
                method: 'DELETE',
                headers: { ...otherAuth, 'If-Match': created.response.headers.get('etag') },
            });
            const updated = await http(itemPath, 200, {
                method: 'PATCH',
                headers: {
                    ...auth,
                    'Content-Type': 'application/json',
                    'If-Match': created.response.headers.get('etag'),
                },
                body: JSON.stringify({ interiorNumber: '4B' }),
            });
            assert.equal(updated.body.interiorNumber, '4B');
            await http(itemPath, 412, {
                method: 'PATCH',
                headers: {
                    ...auth,
                    'Content-Type': 'application/json',
                    'If-Match': created.response.headers.get('etag'),
                },
                body: JSON.stringify({ label: 'Stale edit' }),
            });
            const list = await http(listPath, 200, { headers: auth });
            const replacement = await http(listPath, 201, {
                method: 'POST',
                headers: { ...auth, 'Content-Type': 'application/json', 'If-Match': list.response.headers.get('etag') },
                body: JSON.stringify({ ...addressInput, label: 'Other' }),
            });
            assert.equal((await http(itemPath, 200, { headers: auth })).body.isDefault, false);
            await http(replacement.response.headers.get('location'), 204, {
                method: 'DELETE',
                headers: { ...auth, 'If-Match': replacement.response.headers.get('etag') },
            });
            const unchanged = await http('/api/v1/profiles/me', 200, { headers: auth });
            assert.equal(unchanged.body.contactEmail, 'stack-contact@example.test');
            passed('https-owned-address-crud-default-and-preconditions');
            await assert.rejects(
                new Promise((resolve, reject) => {
                    httpsRequest(origin + '/health/profile/live', { ca: [] }, (response) => {
                        response.resume();
                        resolve();
                    })
                        .on('error', reject)
                        .end();
                }),
            );
            passed('untrusted-gateway-certificate-rejected');
        }
    }
    process.stdout.write(JSON.stringify({ checks }) + '\n');
}
main().catch(() => {
    process.stderr.write('Profile stack HTTP verification failed at ' + operation + '.\n');
    process.exitCode = 1;
});
