# Pixie Demo - Study Partner

A public source variant of Pixie, a study application built by Meesam Abbas.
It includes the FastAPI backend, Next.js interface, database migrations and
process-supervision source. It is a source demonstration, not a hosted service
or a ready-to-deploy production release.

## Included

- Study conversations and stored learning context
- Notes and uploaded study materials
- Calendar, review and learning interfaces
- Authentication and user-scoped application routes

## Configuration

Only dummy configuration templates are included. Environment-variable names
remain because the application needs them; private values are not supplied.
Create a local `.env` from `.env.example`, and `frontend/.env.local` from
`frontend/.env.local.example`. Use credentials you own, a fresh dedicated
Supabase project, a separate PostgreSQL/pgvector database and a separate Honcho
instance/workspace. Replace the example Supabase address in the backend's
Content-Security-Policy with your own project's origin.

The demo database defaults to port 55432 and the demo Honcho instance to port
58000. No infrastructure is provisioned. Python 3.11+, uv, Node.js, PostgreSQL
with pgvector, Honcho and Ollama are needed. Run `uv sync` and `npm ci` from
`frontend/` only after you have reviewed and configured your own environment.
Migrations, providers and application processes are not started automatically.

This snapshot has not been run or approved for public hosting. Do not connect
it to real learner data. It is not a claim of security certification or legal
compliance. API integrations require each user to provide their own credentials.

## Publication boundary

This copy starts with fresh Git history. It excludes the original environment
files, tokens, databases, uploaded files, backups, logs, dependencies, compiled
output, deployment configuration, private planning documents and agent-session
records. The original integration tests were excluded because some referenced
personal paths and a shared local database. No original working-tree changes
are included in this committed-source snapshot.

AI tools support the development process. See LICENSE for reuse terms.
