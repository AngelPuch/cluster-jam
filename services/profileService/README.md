# Profile Service

Profile microservice for Cluster JAM.

This service is responsible for managing customer profiles, contact information, onboarding status, and addresses.

## Technology Stack

- Node.js
- TypeScript
- NestJS
- TypeORM
- PostgreSQL

## Requirements

Install the following tools before running the service locally:

- Node.js LTS
- npm
- PostgreSQL
- Git

NestJS does not need to be installed globally.

## Project Setup

From the `services/profileService` directory, install the project dependencies:

```bash
npm ci
```

If `package-lock.json` has not been generated yet, use:

```bash
npm install
```

## Environment Configuration

Create a `.env` file inside `services/profileService`.

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

The database name and credentials must match your local PostgreSQL configuration.

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

Automatic schema synchronization is disabled with `synchronize: false`.

### Generate a migration

After modifying an entity, generate a migration:

```bash
npm run migration:generate -- src/infrastructure/database/migrations/update-profile -d src/infrastructure/database/typeorm.config.ts
```

Use a descriptive migration name for each schema change.

Review the generated SQL before running the migration, especially when existing records need new required values.

### Run pending migrations

```bash
npm run migration:run -- -d src/infrastructure/database/typeorm.config.ts
```

Previously applied migrations must retain their original names and contents.

## Health Checks

The service exposes two health endpoints.

### Liveness

```http
GET /health/live
```

Checks whether the Profile Service process is running.

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

Checks database connectivity to determine whether the service is ready to receive requests.

Expected response:

```json
{
    "status": "ok"
}
```

## Database Model

Profile Service owns its own PostgreSQL database.

Tables:

- `app.profile`
- `app.address`

### Profile

The `app.profile` table stores:

| Column              | Description                                                |
| ------------------- | ---------------------------------------------------------- |
| `user_id`           | Unique identifier of the user associated with the profile  |
| `name`              | Customer name; nullable while onboarding is pending        |
| `phone`             | Contact phone number; nullable while onboarding is pending |
| `contact_email`     | Email address used for customer contact                    |
| `onboarding_status` | Profile completion status: `PENDING` or `COMPLETED`        |
| `created_at`        | Profile creation timestamp                                 |
| `updated_at`        | Last profile update timestamp                              |

New profiles default to `PENDING`.

Completing onboarding requires a name, phone number, and contact email. The application logic responsible for this transition must validate these values before setting the status to `COMPLETED`.

### Addresses

The `app.address` table stores customer addresses.

A profile can have zero or more addresses.

Each address belongs to a profile through a foreign key within the same database.

At most one address per user can be marked as the default address.

## Architecture

The service follows the Cluster JAM layered architecture.

| Directory                                 | Responsibility                                       |
| ----------------------------------------- | ---------------------------------------------------- |
| `src/interfaces/`                         | HTTP controllers and external entry points           |
| `src/application/`                        | Application use cases                                |
| `src/domain/`                             | Business rules and domain abstractions               |
| `src/infrastructure/`                     | Persistence and implementations of external adapters |
| `src/infrastructure/database/entities/`   | TypeORM entities                                     |
| `src/infrastructure/database/migrations/` | Versioned database migrations                        |
| `src/interfaces/http/health/`             | Health check endpoints                               |

Database configuration is defined in:

- `src/infrastructure/database/typeorm.config.ts`
- `src/infrastructure/database/typeorm.module.ts`

The application entry point is `src/main.ts`, and its root module is `src/app.module.ts`.

Controllers must not access TypeORM repositories directly. Business operations must pass through application use cases.

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
git pull --ff-only origin main
git switch -c feat/profile/manage-profiles
```

Branch naming pattern:

```text
<type>/profile/<description>
```

Examples:

```text
feat/profile/manage-profiles
feat/profile/complete-onboarding
feat/profile/manage-addresses
fix/profile/default-address
docs/profile/document-service-setup
```

Changes must be submitted through a Pull Request and merged using squash merge.
