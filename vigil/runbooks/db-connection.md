# Runbook: PostgreSQL Database Down / Connection Failure

## Severity: Critical

## Symptoms
- Application logs showing "connection refused" or "could not connect to server" errors
- pg_up metric reports 0 in Prometheus
- Database-dependent endpoints returning HTTP 500 errors
- Connection pool exhaustion warnings

## Likely Causes
1. **PostgreSQL process crashed** — OOM killer, disk full, or corrupted WAL
2. **Network issue** — DNS resolution failure or firewall blocking port 5432
3. **Connection pool exhaustion** — Too many idle connections, or connection leak in application code
4. **Configuration change** — Recent changes to pg_hba.conf, postgresql.conf, or connection pool settings
5. **Disk space** — PostgreSQL data directory is full

## Investigation Steps
1. Check if the PostgreSQL container/process is running: `docker compose ps postgres`
2. Check PostgreSQL logs for crash reasons: `docker compose logs postgres --tail=50`
3. Verify connectivity: `pg_isready -h postgres -U vigil`
4. Check disk space on the database volume
5. Look for recent commits that changed database configuration or connection pool settings

## Remediation
1. **If process crashed:** Restart PostgreSQL: `docker compose restart postgres`
2. **If disk full:** Free disk space or expand the volume, then restart
3. **If connection pool exhausted:** Restart the application to release connections, then investigate the connection leak
4. **If configuration error:** Revert the config change and restart PostgreSQL
5. **After restart:** Verify connectivity and monitor for recurrence

## Escalation
- If PostgreSQL fails to start after restart, escalate to the DBA team
- If data corruption is suspected, do NOT attempt repair — escalate immediately
