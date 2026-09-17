# Accounts Service

Accounts microservice for Cluster JAM.

This service is responsible for managing user profiles and addresses. Authentication, credentials, password recovery, and sessions are managed by Supabase Auth.

## Technology Stack

- Node.js
- TypeScript
- NestJS
- TypeORM
- PostgreSQL
- Supabase Auth

## Requirements

Install the following tools before running the service locally:

- Node.js LTS
- npm
- PostgreSQL
- Git

NestJS does not need to be installed globally.

## Project Setup

From the `services/accounts` directory, install the project dependencies:

```bash
npm ci
```

If `package-lock.json` has not been generated yet, use:

```bash
npm install
```

## Environment Configuration

Create a `.env` file inside `services/accounts`.

You can use `.env.example` as a reference.

Example:

```env
APP_ENV=development
HTTP_PORT=8080

DB_HOST=localhost
DB_PORT=5432
DB_NAME=cluster_jam_accounts
DB_USER=accounts
DB_PASSWORD=your_local_password
```

Never commit the `.env` file or real credentials to Git.

## PostgreSQL Setup

For local development, PostgreSQL runs directly on the developer's machine.

Create the application user:

```sql
CREATE USER accounts WITH PASSWORD 'your_local_password';
```

Create the database:

```sql
CREATE DATABASE cluster_jam_accounts
    OWNER accounts;
```

The application uses the `app` PostgreSQL schema.

## Run the Service

Development mode:

```bash
npm run start:dev
```

The REST API runs by default at:

```text
http://localhost:8080
```

## Build

Compile the project:

```bash
npm run build
```

Run the compiled application:

```bash
npm run start:prod
```

## Database Migrations

Database schema changes must be managed through TypeORM migrations.

Automatic schema synchronization is disabled.

### Run pending migrations

```bash
npm run migration:run -- -d src/infrastructure/database/typeorm.config.ts
```

## Health Checks

The service exposes two health endpoints.

### Liveness

```http
GET /health/live
```

Checks whether the Accounts service process is running.

Expected response:

```json
{
    "status": "ok"
}
```

### Readiness

```http
GET /health/ready
```

Checks whether the service is ready to receive requests, including database connectivity.

Expected response:

```json
{
    "status": "ok"
}
```

## Database Model

The Accounts service owns its own PostgreSQL database.

Current tables:

- `app.profile`
- `app.address`

`profile.user_id` stores the validated Supabase JWT `sub` value. It is an external identity reference and is not a foreign key to Supabase.

A profile can have zero or more addresses.

Only one address per user can be marked as the default address.

## Architecture

The service follows the Cluster JAM layered architecture:

```text
src/
├── application/
├── domain/
├── infrastructure/
│   └── database/
│       ├── entities/
│       ├── migrations/
│       ├── typeorm.config.ts
│       └── typeorm.module.ts
├── interfaces/
│   └── http/
|        └── health/
├── app.module.ts
└── main.ts
```

Responsibilities:

- `interfaces`: HTTP controllers and external entry points.
- `application`: application use cases.
- `domain`: business rules and domain abstractions.
- `infrastructure`: PostgreSQL, TypeORM, Supabase, and other external integrations.

Controllers must not access TypeORM repositories directly.

## Authentication

Supabase Auth is the authority for:

- User authentication
- Email used for login
- Passwords
- Password recovery
- Sessions
- User identity

The Accounts database does not store passwords, refresh tokens, or a local copy of Supabase authentication users.

Authenticated operations will use the validated JWT `sub` as the user identifier.

## Tests

Run unit tests:

```bash
npm test
```

Run tests in watch mode:

```bash
npm run test:watch
```

Run test coverage:

```bash
npm run test:cov
```

## Git Workflow

This service follows the repository GitHub Flow.

Create a branch from an updated `main`:

```bash
git switch main
git pull origin main
git switch -c <type>/accounts/<description>
```

Examples:

```text
feat/accounts/integrate-supabase-auth
feat/accounts/manage-profiles
feat/accounts/manage-addresses
fix/accounts/default-address
docs/accounts/document-service-setup
```

Changes must be submitted through a Pull Request and merged using squash merge.
