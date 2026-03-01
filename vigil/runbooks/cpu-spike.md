# Runbook: CPU Spike / High Resource Utilization

## Severity: Warning

## Alert Trigger
- Prometheus alert `HighCpuUsage` fires when container CPU exceeds 80% sustained for 2+ minutes
- Often accompanied by `HighLatency` alert when request p95 exceeds 5 seconds

## Symptoms
- Container CPU utilization sustained above 80-90% for multiple minutes
- Request latency spike: p95 jumps from ~120ms baseline to 5-10+ seconds
- Worker processes consuming 90%+ CPU — visible with `top` or `docker stats`
- Health check response time degraded (> 500ms threshold)
- Requests queuing behind CPU-bound handlers — nginx reporting upstream timeout
- Specific endpoint(s) identified as the bottleneck in access logs

## Likely Causes
1. **CPU-bound synchronous processing** — An endpoint processes large datasets in-memory without async offloading (e.g., JSON serialization of full database dumps, report generation, CSV export)
2. **Infinite loop or runaway process** — Bug in application code causing unbounded CPU usage (tight loop without sleep, recursive function without base case)
3. **Unoptimized data transformation** — Code processing large payloads synchronously (e.g., `transform_batch()` on 50MB+ datasets without pagination or streaming)
4. **Traffic spike without rate limiting** — Sudden burst of requests overwhelming the service's compute capacity
5. **Regex backtracking** — Complex regex patterns causing exponential CPU on certain input strings (ReDoS)

## Investigation Steps
1. **Identify the hot process**: `docker compose exec flask-app top -b -n 1` — which PID is consuming CPU?
2. **Check request logs**: Which endpoint is being hit repeatedly or taking unusually long? Look for requests taking > 5s
3. **Check recent commits**: Look for changes to `data_processor.py`, `handlers/`, `routes/reports.py`, or any endpoint that processes data
4. **Profile the bottleneck**: If a specific endpoint is identified, check if it's doing synchronous heavy computation (large JSON serialization, dataset transformation, report generation)
5. **Check traffic volume**: Is this a traffic spike or a code change? Compare request rates to baseline

## Remediation
1. **If caused by CPU-bound endpoint**: Move the heavy processing to an async background worker — return `202 Accepted` with a job ID instead of processing inline
2. **If caused by large payload processing**: Add pagination, streaming, or payload size limits. Break `transform_batch()` into smaller chunks
3. **If caused by traffic spike**: Enable or tighten rate limiting. Scale up horizontally if the load is legitimate
4. **If caused by runaway process**: Restart the container — `docker compose restart flask-app`. Then investigate and fix the loop/recursion bug
5. **Temporary relief**: Restart the service to clear the CPU spike while investigating root cause. Monitor that CPU returns to baseline within 2 minutes

## Escalation
- If CPU remains elevated after container restart and code revert, escalate to the platform team
- If this is a recurring pattern (3+ times in a week), create a performance optimization ticket
- If the endpoint is customer-facing and latency exceeds SLA, notify the product team
