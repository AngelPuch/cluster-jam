import { existsSync } from 'node:fs';
import { loadEnvFile } from 'node:process';
import { DataSource } from 'typeorm';
import { createDatabaseOptions } from './typeorm.options';

if (existsSync('.env')) loadEnvFile('.env');

export const AppDataSource = new DataSource(createDatabaseOptions());
