# Runbook: High 5xx Error Rate

## Severity: Critical

## Symptoms
- HTTP 500 error rate exceeds normal threshold
- Users reporting application errors or blank pages
- Error logs showing unhandled exceptions or service crashes

## Likely Causes
1. **Bad deployment** — A recent code change introduced a bug in error handling or request processing
2. **Downstream service failure** — A dependency (database, cache, external API) is unreachable
3. **Resource exhaustion** — Memory or CPU limits reached, causing the application to crash
4. **Configuration error** — Incorrect environment variables or misconfigured middleware

## Investigation Steps
1. Check application logs for stack traces: `search_logs("ERROR 500 exception", "15m")`
2. Correlate with recent deployments: check the last 5 commits for changes to error handlers, middleware, or API routes
3. Verify downstream dependencies are healthy (database, cache, external services)
4. Check resource utilization (CPU, memory) on the application containers

## Remediation
1. **If caused by bad deploy:** Roll back to the previous version immediately
2. **If caused by downstream failure:** Check and restart the failing dependency
3. **If caused by resource exhaustion:** Scale up containers or restart the affected service
4. **If cause is unknown:** Enable debug logging, capture a full request trace, and escalate

## Escalation
- If error rate does not decrease within 10 minutes of remediation, escalate to the platform team
- Notify the product team if user-facing impact exceeds 5 minutes
