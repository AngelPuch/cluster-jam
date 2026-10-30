import { closeSync, fstatSync, openSync, readSync } from 'node:fs';

export function resolveSecretFiles(input: Record<string, unknown>, names: readonly string[]): Record<string, unknown> {
    const resolved = { ...input };
    for (const name of names) {
        const path = resolved[`${name}_FILE`];
        if (path === undefined || path === '') continue;
        if (typeof path !== 'string' || (resolved[name] !== undefined && resolved[name] !== '')) {
            throw new Error(`Invalid secret configuration: ${name}`);
        }
        let descriptor: number | undefined;
        try {
            descriptor = openSync(path, 'r');
            if (!fstatSync(descriptor).isFile()) throw new Error();
            const bytes = Buffer.alloc(8193);
            const length = readSync(descriptor, bytes, 0, bytes.length, 0);
            if (length < 1 || length > 8192) throw new Error();
            const value = bytes
                .subarray(0, length)
                .toString('utf8')
                .replace(/\r?\n$/, '');
            if (!value.trim() || /[\r\n\0]/.test(value)) throw new Error();
            resolved[name] = value;
        } catch {
            throw new Error(`Cannot load secret file: ${name}`);
        } finally {
            if (descriptor !== undefined) closeSync(descriptor);
        }
    }
    return resolved;
}
