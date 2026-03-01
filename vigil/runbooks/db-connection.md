# Runbook: PostgreSQL Database Down / Connection Failure

## Severity: Critical

## Alert Trigger
- Prometheus alert `PostgresDown` fires when `pg_up == 0` for more than 30 seconds
- Postgres-exporter reports connection failure to PostgreSQL at `postgres:5432`

## Symptoms
- Application logs showing `psycopg2.OperationalError: Connection refused` or `could not connect to server`
- `pg_up` metric reports 0 in Prometheus (pg_isready failing)
- All database-dependent API endpoints returning HTTP 500 with "connection refused" errors
- Connection pool reporting 0 available connections — all connections dead or timed out
- Flask-app cascading failure: every request that touches the database fails

## Likely Causes
1. **PostgreSQL container stopped or crashed** — OOM killer terminated the process, disk full, or corrupted WAL logs
2. **Connection pool misconfiguration** — Recent config change set `max_connections` too high or removed `idle_timeout`, exhausting shared memory
3. **pg_hba.conf change** — Authentication config accidentally removed the app's subnet, blocking all connections
4. **Disk space exhaustion** — PostgreSQL data directory full, causing write failures and crash
5. **Network partition** — DNS resolution failure or Docker network issue blocking port 5432

## Investigation Steps
1. **Check if PostgreSQL container is running**: `docker compose ps postgres` — is it running or has it exited?
2. **Check PostgreSQL container logs**: `docker compose logs postgres --tail=50` — look for `FATAL`, `could not`, or `out of memory`
3. **Test connectivity**: `docker compose exec postgres pg_isready -U vigil` — confirms if the process is accepting connections
4. **Check recent commits**: Look for changes to `config/database.py`, `docker-compose.yml`, `postgresql.conf`, or connection pool settings
5. **Check disk space**: `docker compose exec postgres df -h /var/lib/postgresql/data`

## Remediation
1. **If PostgreSQL process crashed**: Restart the container — `docker compose restart postgres`. Monitor logs for restart success
2. **If connection pool misconfigured**: Revert the config change (e.g., restore `max_connections` to 25, re-add `idle_timeout=30s`). Restart both postgres and the application
3. **If pg_hba.conf changed**: Revert the auth config, then `docker compose exec postgres pg_ctl reload`
4. **If disk full**: Free disk space or expand the volume, then restart PostgreSQL
5. **After any fix**: Verify connectivity with `pg_isready`, then restart the application to re-establish the connection pool

## Escalation
- If PostgreSQL fails to start after restart, escalate to the DBA team immediately
- If data corruption is suspected (WAL errors, checkpoint failures), do NOT attempt repair — escalate immediately
- If this is the 3rd occurrence this month, create a capacity planning ticket for the database team
