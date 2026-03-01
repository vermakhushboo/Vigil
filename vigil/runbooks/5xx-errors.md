# Runbook: High 5xx Error Rate (HTTP 500/502/503)

## Severity: Critical

## Alert Trigger
- Prometheus alert `High5xxRate` fires when 5xx error count exceeds 5 in 60 seconds
- Typically affects `flask-app` service behind nginx reverse proxy

## Symptoms
- HTTP 500 (Internal Server Error) responses on multiple API endpoints
- HTTP 502 (Bad Gateway) from nginx when flask-app is crashing
- Users seeing "Something went wrong" or blank error pages
- Application error logs showing `AttributeError`, `TypeError`, or unhandled exceptions
- Error rate spike correlating with a recent deployment timestamp

## Likely Causes
1. **Bad deployment — broken error handler or middleware** — A recent code change introduced a bug in the request processing pipeline. Common pattern: removed a null check, changed exception handling, or introduced a type mismatch in middleware
2. **Malformed request body handling** — Error handler crashes on unexpected input (null body, wrong content-type)
3. **Downstream dependency failure** — Database or external API unreachable, causing unhandled exceptions in request handlers
4. **Misconfigured environment variables** — Missing or incorrect config after deploy (API keys, database URLs, feature flags)

## Investigation Steps
1. **Check error logs for stack traces**: Search for "500", "ERROR", "exception" in recent logs — look for the specific file and line number crashing
2. **Correlate with recent deploys**: Check last 5 git commits — focus on changes to `error_handler.py`, `middleware/`, `routes/`, or any request processing code
3. **Identify the pattern**: Are ALL endpoints returning 500, or just specific ones? If all endpoints fail, the bug is likely in shared middleware. If specific endpoints fail, the bug is in that route handler
4. **Check if health endpoint is affected**: If `/health` also returns 500, the middleware itself is broken (critical — affects all routes)

## Remediation
1. **If caused by a bad deploy**: Roll back to previous version immediately — `git revert <sha>` and redeploy
2. **If caused by broken error handler middleware**: The error handler itself is crashing instead of catching errors. Restore the null checks or exception handling that was removed
3. **If caused by downstream failure**: Check and restart the failing dependency (database, cache, external API)
4. **If cause is unknown**: Enable debug logging, capture a full request trace, and restart the service as temporary relief

## Escalation
- If error rate does not decrease within 10 minutes of rollback, escalate to the platform team
- Notify the product team immediately if user-facing impact exceeds 5 minutes
- If the root cause is in shared middleware, all API consumers may be affected — check downstream services
