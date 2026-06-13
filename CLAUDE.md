
# Database Project

## Project Type
Database-centric project for schema design, migrations, query optimization, and database administration.

## Project-Specific Standards

### Database Engine
- PostgreSQL (recommended), MySQL, or SQLite
- Use engine-specific features where they add value
- Document minimum version requirements in README

### Project Structure
- migrations/ (numbered: 001-create-users.sql, 002-add-indexes.sql)
- schemas/ (current schema definitions, one file per table/domain)
- queries/ (reusable queries organized by domain)
- seeds/ (test/development data)
- scripts/ (maintenance scripts, backups, health checks)
- tests/ (query tests, constraint tests)

### Schema Design
- Every table has a primary key (prefer UUID or BIGSERIAL)
- Foreign keys with appropriate ON DELETE/UPDATE actions
- NOT NULL by default; allow NULL only with documented reason
- Indexes on all foreign keys and frequently queried columns
- CHECK constraints for data integrity
- Consistent naming: snake_case, plural table names, singular column names

### Migration Practices
- One migration per logical change (don't combine unrelated changes)
- Migrations are forward-only in production (no DROP in production migrations)
- Include both UP and DOWN migrations for development
- Test migrations against a copy of production data
- Document breaking changes in migration comments

### Query Standards
- Use CTEs for readability over deeply nested subqueries
- EXPLAIN ANALYZE for any query touching large tables
- Parameterized queries always (never string interpolation)
- Appropriate use of indexes (check query plans)
- Avoid SELECT * in application queries

### Testing Strategy
- Test constraints: Verify NOT NULL, UNIQUE, CHECK, FK constraints
- Test queries: Expected results with known test data
- Test migrations: Run up and down on test database
- Performance tests: Query plans stay efficient as data grows
- Use pgTAP (PostgreSQL) or similar for database unit tests

### Documentation Requirements
- README.md: Database purpose, how to set up locally, connection info
- documentation/
  - schema.md: Entity descriptions, relationships, design decisions
  - migrations.md: Migration conventions, how to create and run
  - queries.md: Common query patterns, performance notes
  - development.md: Local setup, seeding test data, running tests

### Performance
- Index strategy documented per table
- Regular ANALYZE/VACUUM schedule (PostgreSQL)
- Connection pooling (PgBouncer or application-level)
- Slow query logging enabled in development
- Partition large tables when appropriate

### Security
- Least privilege: Application user has minimal required permissions
- Row-level security where applicable
- No credentials in code or migrations (use environment variables)
- Audit columns (created_at, updated_at) on all tables

### Quality Gates (Before Next Change)
- [ ] Migration runs cleanly (up and down)
- [ ] All constraints tested
- [ ] Query performance verified (EXPLAIN ANALYZE)
- [ ] Schema documentation updated
- [ ] Seed data updated if schema changed
- [ ] No raw SQL injection vectors

### Cost Considerations
- Local PostgreSQL or SQLite for development (free)
- Cloud: Supabase, Neon, or PlanetScale free tiers
- Monitor query costs and connection counts in production
