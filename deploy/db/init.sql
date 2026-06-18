-- yuleOSH PostgreSQL initialization script
-- This runs automatically on first container start.

-- Create extension for UUID generation (if available)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- The Store class auto-creates tables via migrations, but we seed
-- the initial schema here for docker-entrypoint-initdb.d compatibility.
-- All additional tables are created dynamically by the application.

-- Ensure we're connected to the right database
\c yuleosh;

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE yuleosh TO yuleosh;
GRANT ALL PRIVILEGES ON SCHEMA public TO yuleosh;
