import type { Channel } from 'amqplib';
import topology from './profile-topology.json';

export { topology as PROFILE_TOPOLOGY };

export async function declareProfileTopology(
    channel: Channel,
    retryDelays: readonly number[] = topology.retries.map((retry) => retry.delayMs),
): Promise<void> {
    if (retryDelays.length !== 2 || retryDelays.some((delay) => !Number.isSafeInteger(delay) || delay <= 0)) {
        throw new Error('Invalid retry topology');
    }
    // Auth/infrastructure owns the identity exchange. Profile only reads it.
    await channel.checkExchange(topology.exchange);
    for (const exchange of topology.exchanges) {
        await channel.assertExchange(exchange.name, exchange.type, { durable: exchange.durable });
    }
    for (const queue of topology.queues) {
        const index = topology.retries.findIndex((retry) => retry.queue === queue.name);
        await channel.assertQueue(queue.name, {
            durable: queue.durable,
            arguments: { ...queue.arguments, ...(index >= 0 ? { 'x-message-ttl': retryDelays[index] } : {}) },
        });
    }
    for (const binding of topology.bindings) {
        await channel.bindQueue(binding.destination, binding.source, binding.routing_key);
    }
}
