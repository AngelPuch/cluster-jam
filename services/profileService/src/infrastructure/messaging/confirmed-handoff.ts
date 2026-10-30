import type { ConfirmChannel, ConsumeMessage } from 'amqplib';

export async function confirmedHandoff(
    channel: ConfirmChannel,
    message: ConsumeMessage,
    exchange: string,
    routingKey: string,
    headers: Record<string, unknown>,
    timeoutMs = 5000,
): Promise<void> {
    // Called serially on a prefetch=1 consumer channel. Any return belongs to
    // this handoff. Never ACK the original if routing or confirmation is uncertain.
    await new Promise<void>((resolve, reject) => {
        let returned = false;
        const onReturn = (): void => {
            returned = true;
        };
        const cleanup = (): void => {
            clearTimeout(timer);
            channel.off('return', onReturn);
            channel.off('close', onClose);
        };
        const fail = (): void => {
            cleanup();
            reject(new Error('REGISTRATION_HANDOFF_FAILED'));
        };
        const onClose = (): void => fail();
        const timer = setTimeout(fail, timeoutMs);
        channel.on('return', onReturn);
        channel.once('close', onClose);
        const original: { readonly [K in keyof ConsumeMessage['properties']]: unknown } = message.properties;
        const stringProperty = (value: unknown): string | undefined => (typeof value === 'string' ? value : undefined);
        const originalHeaders =
            typeof original.headers === 'object' && original.headers !== null
                ? (original.headers as Record<string, unknown>)
                : {};
        try {
            channel.publish(
                exchange,
                routingKey,
                message.content,
                {
                    persistent: true,
                    mandatory: true,
                    messageId: stringProperty(original.messageId),
                    type: stringProperty(original.type),
                    contentType: stringProperty(original.contentType),
                    contentEncoding: stringProperty(original.contentEncoding),
                    correlationId: stringProperty(original.correlationId),
                    timestamp: typeof original.timestamp === 'number' ? original.timestamp : undefined,
                    appId: stringProperty(original.appId),
                    headers: { ...originalHeaders, ...headers },
                },
                (error: unknown) => {
                    if (error || returned) fail();
                    else {
                        cleanup();
                        resolve();
                    }
                },
            );
        } catch {
            fail();
        }
    });
}
