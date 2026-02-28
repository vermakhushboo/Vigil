# Runbook: CPU Spike / High Resource Utilization

## Severity: Warning

## Symptoms
- CPU utilization exceeds 80% sustained for more than 2 minutes
- Request latency increases significantly (p95 > 5 seconds)
- Application becomes unresponsive or slow
- Container health checks start failing

## Likely Causes
1. **Compute-heavy request** — An endpoint is performing expensive calculations without async processing
2. **Infinite loop or runaway process** — Bug in application code causing unbounded CPU usage
3. **Traffic spike** — Sudden increase in request volume overwhelming the service
4. **Memory pressure** — Excessive garbage collection due to memory leaks
5. **Bad query** — Unoptimized database query causing CPU-intensive processing

## Investigation Steps
1. Check which process is consuming CPU: `docker compose exec flask-app top`
2. Look for recent code changes that introduced compute-heavy operations
3. Check request logs for unusual traffic patterns or repeated requests to specific endpoints
4. Monitor request latency to identify which endpoints are affected
5. Check if the issue correlates with a recent deployment

## Remediation
1. **If caused by a specific endpoint:** Identify and optimize the endpoint, add caching or async processing
2. **If caused by traffic spike:** Scale up horizontally, enable rate limiting
3. **If caused by runaway process:** Restart the affected container: `docker compose restart flask-app`
4. **If caused by bad query:** Identify the query, add proper indexing, or optimize the query plan
5. **Temporary relief:** Restart the service to clear the spike while investigating root cause

## Escalation
- If CPU remains elevated after container restart, escalate to the platform team
- If this is a recurring pattern (3+ times in a week), create a ticket for performance optimization
