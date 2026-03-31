# 🏗️ Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VERCEL DEPLOYMENT                            │
│                     (Serverless + Edge Network)                      │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
         ┌──────────▼─────────┐       ┌──────────▼─────────┐
         │   Static Assets     │       │   API Functions    │
         │   (CDN Cached)      │       │   (Python/Flask)   │
         │                     │       │                     │
         │  • index.html       │       │  • /api/summary    │
         │  • CSS/JS inline    │       │  • /api/segments   │
         │  • Chart.js         │       │  • /api/cltv_dist  │
         │  • Dark UI theme    │       │  • /api/download   │
         └─────────────────────┘       │  • ... 10 more     │
                                       └──────────┬─────────┘
                                                  │
                                   Connection Pooling (5 min cache)
                                                  │
                                       ┌──────────▼─────────┐
                                       │   Amazon Redshift   │
                                       │   (Data Warehouse)  │
                                       │                     │
                                       │  Host: ea-non-prod  │
                                       │  DB: express        │
                                       │  Table: KIRAN.      │
                                       │    TBL_CUSTOMER_    │
                                       │    PROFILE          │
                                       │                     │
                                       │  15,338,254 rows    │
                                       └──────────┬─────────┘
                                                  │
                                   Updated by Pipeline (gpu01)
                                                  │
                         ┌────────────────────────┼────────────────────────┐
                         │                        │                        │
              ┌──────────▼─────────┐   ┌─────────▼────────┐   ┌──────────▼─────────┐
              │   Step 1: RFM/CLTV  │   │  Step 2: Churn   │   │  Step 3: Browse/   │
              │   (~40 min)         │   │  (~25 min)       │   │  Email (~45 min)   │
              │                     │   │                  │   │                     │
              │  • Recency score    │   │  • XGBoost model │   │  • Browse signals  │
              │  • Frequency score  │   │  • Churn prob    │   │  • Email engage    │
              │  • Monetary score   │   │  • Risk segment  │   │  • Engagement mult │
              │  • CLTV predicted   │   │  • 19 features   │   │  • Cart signals    │
              │  • RFM segments     │   │                  │   │                     │
              └─────────────────────┘   └──────────────────┘   └─────────────────────┘
```

---

## Data Flow

### User Request → Live Data Response

```
1. User opens:  https://lampsplus-customer-dashboard.vercel.app
                                   ↓
2. Vercel CDN serves:  index.html (cached at edge, instant)
                                   ↓
3. Browser loads page:  Dark UI renders, shows loading state
                                   ↓
4. JavaScript fetches:  /api/summary (AJAX request)
                                   ↓
5. Vercel Function:  api/index.py → Flask route handler
                                   ↓
6. Connection pool:  Check if cached connection exists (<5 min old)
                     ├─ Yes → Reuse connection (~500ms)
                     └─ No  → Create new connection (~2-3 sec)
                                   ↓
7. Execute query:  SELECT COUNT(*), AVG(cltv_adjusted_v2), ...
                   FROM KIRAN.TBL_CUSTOMER_PROFILE
                   WHERE [activity filter]
                                   ↓
8. Redshift returns:  Result set (aggregated data)
                                   ↓
9. Pandas DataFrame:  Convert to dict, format numbers
                                   ↓
10. JSON response:  {"total": 15338254, "avg_cltv": 247.89, ...}
                                   ↓
11. Browser renders:  KPI cards, charts, segment breakdown
                                   ↓
12. User sees:  Live data from Redshift (refreshed on every page load)
```

---

## Pipeline → Dashboard Update Flow

### How Dashboard Reflects New Pipeline Runs

```
1. Manual pipeline run (gpu01):
   
   spark-submit rfm_cltv_tbl_customer_profile.py
                                   ↓
   PySpark processes 15.3M rows → generates scores → writes to S3
                                   ↓
   Redshift COPY from S3 → staging table
                                   ↓
   UPDATE KIRAN.TBL_CUSTOMER_PROFILE SET ... FROM staging
                                   ↓
   Sets update_date = CURRENT_TIMESTAMP
                                   ↓
   (Pipeline completes ~40 minutes later)

2. Dashboard reflects changes IMMEDIATELY:
   
   Next page load → /api/summary query → reads updated rows
                                   ↓
   Dashboard shows new data (no deploy needed!)
                                   ↓
   "Last Refresh" timestamp updates automatically
```

**Key insight**: Dashboard queries Redshift on every request, so pipeline updates appear instantly without any deployment or cache invalidation.

---

## Performance Characteristics

### Query Response Times

| Endpoint | Cold Start | Warm (Cached Connection) | Notes |
|----------|-----------|--------------------------|-------|
| `/api/health` | 2-3 sec | 200-300 ms | Simple SELECT 1 |
| `/api/summary` | 2-3 sec | 800ms-1.2s | Aggregates 15M rows |
| `/api/segments` | 2-3 sec | 1-1.5s | GROUP BY with 9 segments |
| `/api/top_customers` | 2-3 sec | 600-900ms | ORDER BY LIMIT 20 |
| `/api/download` | 2-3 sec | 2-5s | Fetches 100-500 rows + PII join |

**Cold start**: First request or after 5 min idle (Vercel function spin-up + Redshift handshake)  
**Warm**: Subsequent requests (reuses connection pool)

### Optimization Strategies Applied

1. **Connection Pooling**: Cache Redshift connections for 5 minutes
2. **Indexed Queries**: Use `master_customer_id` (PK) for lookups
3. **Aggregation Pushdown**: Redshift computes COUNT/AVG/SUM (not client-side)
4. **Result Limiting**: Max 500 rows for downloads, 20 for top customers
5. **No N+1 Queries**: Single query per endpoint (no loops)

---

## Security Model

### Current Implementation (Development)

```
┌─────────────┐
│   Browser   │  User opens dashboard URL
└──────┬──────┘
       │ HTTPS (enforced by Vercel)
       ↓
┌─────────────┐
│ Vercel Edge │  TLS termination, DDoS protection
└──────┬──────┘
       │ Internal Vercel network
       ↓
┌─────────────┐
│  API Lambda │  Environment variables (encrypted at rest)
└──────┬──────┘
       │ Redshift driver (redshift-connector)
       ↓
┌─────────────┐
│  Redshift   │  Standard authentication (user/password)
└─────────────┘
```

**What's secure**:
- ✅ HTTPS enforced (no plain HTTP)
- ✅ Credentials stored in Vercel environment (not in code)
- ✅ Redshift connection encrypted in transit
- ✅ No API keys exposed to browser

**What's NOT secure** (needs hardening):
- ⚠️ No authentication (anyone with URL can access)
- ⚠️ Uses write-enabled Redshift credentials
- ⚠️ PII data downloadable without audit log

### Recommended Production Security

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTPS
       ↓
┌─────────────┐
│ Vercel Edge │  IP whitelist (optional)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  API Lambda │  HTTP Basic Auth (username/password prompt)
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  Redshift   │  Read-only user (dashboard_readonly)
└─────────────┘
       │
       ↓ Audit logs
┌─────────────┐
│  CloudWatch │  Track who downloaded what (IP, timestamp, segment)
└─────────────┘
```

**See README.md → "Security Best Practices"** for implementation code.

---

## Deployment Workflow

### Continuous Deployment Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  Developer Workflow (on gpu01)                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
         1. Make changes      │
         nano api/index.py    │
                              ↓
         2. Test locally      │
         python local_dev.py  │
                              ↓
         3. Commit & push     │
         git commit -m "..."  │
         git push origin main │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Repository (kiran-EA/lampsplus-customer-dashboard)      │
└─────────────────────────────────────────────────────────────────┘
                              │
         Webhook trigger      │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Vercel Build Pipeline                                          │
│                                                                 │
│  1. Clone repo                                                  │
│  2. pip install -r requirements.txt                             │
│  3. Bundle api/index.py → Serverless function                   │
│  4. Copy public/ → CDN                                          │
│  5. Inject environment variables                                │
│  6. Deploy to production URL                                    │
│                                                                 │
│  ⏱️ Build time: ~60-90 seconds                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
         Deploy complete      │
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  Live Dashboard: https://lampsplus-customer-dashboard.vercel.app│
└─────────────────────────────────────────────────────────────────┘
```

**Key features**:
- ✅ Zero-downtime deployments (new version goes live atomically)
- ✅ Automatic rollback on build failure
- ✅ Preview deployments for branches (test before merging)
- ✅ Deployment notifications (email, Slack)

---

## Scalability & Limits

### Vercel Hobby Plan Limits

| Resource | Limit | Dashboard Usage | Headroom |
|----------|-------|-----------------|----------|
| Serverless execution | 100 GB-hours/month | ~10 GB-hours | 90% available |
| Function timeout | 10 seconds | 1-5 sec per request | ✅ Safe |
| Bandwidth | 100 GB/month | ~5 GB/month | ✅ Safe |
| Requests | Unlimited | ~50K/month (internal) | ✅ Safe |

### Redshift Query Performance

| Row Count | Aggregation Query | With Index |
|-----------|-------------------|------------|
| 15.3M rows | 1.5-2.5 sec | 800ms-1.2s |
| Filter: 1 year (3M rows) | 800ms-1.2s | 400-700ms |
| Top 20 ORDER BY | 600-900ms | 300-500ms |

**Recommendation**: Current setup handles 100+ concurrent users comfortably. For >500 users, upgrade to Vercel Pro + Redshift RA3 nodes.

---

## Cost Breakdown

### Monthly Costs (Current Setup)

| Service | Plan | Cost | Notes |
|---------|------|------|-------|
| Vercel | Hobby | **$0** | 100 GB-hours execution, HTTPS, custom domains |
| Redshift | Existing cluster | **$0** | Already running for other workloads |
| Data transfer | Negligible | **$0** | <1 GB/month dashboard queries |
| **Total** | | **$0/month** | |

### If Scaling Up

| Service | Plan | Cost | Use Case |
|---------|------|------|----------|
| Vercel | Pro | $20/month | 60-sec timeout, 1000 GB-hours, team collaboration |
| Redshift | RA3.xlplus | +$1.50/hr | Faster queries, 500+ concurrent users |

---

## Monitoring & Observability

### Built-in Vercel Metrics

1. **Function Logs**: Real-time Python print/error output
   - Path: Dashboard → Project → Deployments → Latest → "Function Logs"
   - Shows: Query execution times, errors, connection status

2. **Analytics**: Request count, response times, error rates
   - Path: Dashboard → Project → "Analytics"
   - Shows: P50/P95/P99 latency, 4xx/5xx errors

3. **Deployment History**: All builds, commit messages, rollback capability
   - Path: Dashboard → Project → "Deployments"

### Adding Custom Monitoring (Optional)

```python
# In api/index.py
import time

@app.before_request
def log_request():
    request.start_time = time.time()

@app.after_request
def log_response(response):
    duration = time.time() - request.start_time
    print(f"[METRICS] {request.method} {request.path} → {response.status_code} ({duration:.3f}s)")
    return response
```

---

## Disaster Recovery

### Data Loss Scenarios

| Scenario | Impact | Recovery |
|----------|--------|----------|
| Vercel app deleted | Dashboard down | Redeploy from GitHub (5 min) |
| Redshift table dropped | No data | Restore from backup or re-run pipeline |
| GitHub repo deleted | Source code lost | ❌ CRITICAL (backup code locally) |
| Environment vars wiped | Dashboard broken | Re-add from .env.example (2 min) |

### Backup Strategy

```bash
# Weekly backup of deployment files
cd /home/devmgr/KiranDev/customer_profile
git clone https://github.com/kiran-EA/lampsplus-customer-dashboard.git backup-$(date +%Y%m%d)

# Backup environment variables
echo "REDSHIFT_HOST=..." > .env.backup
```

---

## Future Enhancements

### Roadmap

1. **Caching Layer** (Redis)
   - Cache KPIs for 5 minutes → reduce Redshift load
   - Estimated cost: $0-5/month (Upstash free tier)

2. **User Authentication** (NextAuth.js)
   - Email/password login
   - Role-based access (admin vs viewer)
   - Estimated effort: 4-6 hours

3. **Scheduled Data Refresh** (Vercel Cron)
   - Trigger pipeline from Vercel at 2 AM daily
   - Requires: SSH access to gpu01 from Vercel function
   - Estimated effort: 2-3 hours

4. **Email Alerts** (SendGrid)
   - "High-risk customer churn alert"
   - "Pipeline completion notification"
   - Estimated cost: $0 (SendGrid free tier)

5. **Custom Domain**
   - `dashboard.lampsplus.com`
   - Requires: DNS configuration (5 min)
   - Cost: $0 (included in Vercel Hobby)

---

## Questions & Support

**Architecture questions**: See README.md  
**API documentation**: README.md → "API Endpoints"  
**Deployment help**: DEPLOY.md  
**Security guidance**: README.md → "Security Best Practices"  

**Created by**: Kiran Pramod Mangalavedhe  
**Team**: Data Engineering @ LampsPlus  
