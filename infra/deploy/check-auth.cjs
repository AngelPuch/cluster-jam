"use strict";

const fs = require("node:fs");
const { Pool } = require("pg");
const amqp = require("amqplib");

async function main() {
    const timeout = setTimeout(() => process.exit(1), 15000);
    let pool;
    let connection;
    let channel;
    try {
        pool = new Pool({
            connectionString: fs
                .readFileSync(process.env.OUTBOX_DATABASE_URL_FILE, "utf8")
                .trim(),
            ssl: {
                rejectUnauthorized: true,
                ca: fs.readFileSync(
                    process.env.OUTBOX_DATABASE_CA_PATH,
                    "utf8",
                ),
            },
            connectionTimeoutMillis: 5000,
            query_timeout: 5000,
            max: 1,
        });
        pool.on("error", () => {
            process.exitCode = 1;
        });
        await pool.query("SELECT 1");
        const url = fs
            .readFileSync(process.env.RABBITMQ_URL_FILE, "utf8")
            .trim();
        connection = await amqp.connect(url, { timeout: 5000 });
        connection.on("error", () => {
            process.exitCode = 1;
        });
        channel = await connection.createChannel();
        channel.on("error", () => {
            process.exitCode = 1;
        });
        await channel.checkExchange("identity.events");
        process.stdout.write("Auth SQL TLS and AMQPS checks passed.\n");
    } catch {
        process.stderr.write(
            "Auth dependency checks failed; inspect configuration without logging secrets.\n",
        );
        process.exitCode = 1;
    } finally {
        await channel?.close().catch(() => {});
        await connection?.close().catch(() => {});
        await pool?.end().catch(() => {});
        clearTimeout(timeout);
    }
}

main().catch(() => {
    process.stderr.write("Auth dependency check could not complete.\n");
    process.exitCode = 1;
});
