-- OutreachAI – PostgreSQL initialization script
-- Runs on first container start

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";        -- PGVector for embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- Trigram for fuzzy search

-- Create application schema
-- (Tables are created by Alembic migrations, not here)

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE outreachai TO outreach;
