# 🔧 Troubleshooting Guide - Vercel Deployment Failures

## Quick Diagnosis Checklist

Run through this checklist to identify your issue:

- [ ] Files uploaded to gpu01?
- [ ] GitHub repository created?
- [ ] Vercel account connected to GitHub?
- [ ] Environment variables configured in Vercel?
- [ ] Build logs show specific error?

---

## Common Failure Scenarios & Fixes

### 🔴 Issue 1: Vercel Build Fails - "No Python version specified"

**Symptoms**:
- Build logs show: `Error: Python version not found`
- Deployment fails during build phase

**Cause**: Missing `runtime.txt` file

**Fix**:
```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Create runtime.txt
echo "python-3.11" > runtime.txt

git add runtime.txt
git commit -m "Add Python runtime version"
git push origin main
```

---

### 🔴 Issue 2: Vercel Build Fails - "Module not found: redshift_connector"

**Symptoms**:
- Build logs show: `ModuleNotFoundError: No module named 'redshift_connector'`
- Requirements installation failed

**Cause**: Vercel uses `pip` but some packages need specific versions

**Fix - Option A (Update requirements.txt)**:
```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Edit requirements.txt - use specific versions that work on Vercel
cat > requirements.txt << 'EOF'
Flask==3.0.0
Werkzeug==3.0.1
redshift-connector==2.0.918
pandas==2.1.4
numpy==1.26.2
pytz==2023.3
EOF

git add requirements.txt
git commit -m "Fix: Pin dependency versions"
git push origin main
```

**Fix - Option B (Add vercel.json build config)**:
```bash
# Update vercel.json to ensure pip install runs
cat > vercel.json << 'EOF'
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python",
      "config": {
        "maxLambdaSize": "50mb"
      }
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "api/index.py"
    },
    {
      "src": "/(.*)",
      "dest": "public/$1"
    }
  ]
}
EOF

git add vercel.json
git commit -m "Fix: Update Vercel build config"
git push origin main
```

---

### 🔴 Issue 3: Dashboard Loads But Shows "Internal Server Error" on API Calls

**Symptoms**:
- Dashboard HTML loads fine
- API endpoints return 500 error
- Browser console shows: `Failed to fetch /api/summary`

**Cause**: Missing environment variables or Redshift connection failure

**Fix - Check Vercel Environment Variables**:

1. Go to: https://vercel.com/dashboard
2. Click your project: `lampsplus-customer-dashboard`
3. Click: **Settings** → **Environment Variables**
4. Verify these are set:

```
REDSHIFT_HOST = ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com
REDSHIFT_PORT = 5439
REDSHIFT_DATABASE = express
REDSHIFT_USER = easuper
REDSHIFT_PASSWORD = LAMRedPWD@2024
```

5. If missing, click **Add** and set them
6. **IMPORTANT**: Check ALL three environments:
   - ✅ Production
   - ✅ Preview
   - ✅ Development

7. After adding, **redeploy**:
   - Go to: **Deployments**
   - Click ⋮ on latest deployment
   - Click **Redeploy**

---

### 🔴 Issue 4: Vercel Build Succeeds But Function Times Out (504 Error)

**Symptoms**:
- Build succeeds (green checkmark)
- Dashboard loads
- API calls timeout after 10 seconds
- Error: `FUNCTION_INVOCATION_TIMEOUT`

**Cause**: Redshift query takes >10 seconds (Hobby plan limit)

**Fix - Optimize Queries**:

Run these on Redshift to add indexes:

```sql
-- Connect to Redshift
psql -h ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com \
     -U easuper -d express -p 5439

-- Add indexes
CREATE INDEX idx_rfm_segment_v2 ON kiran.tbl_customer_profile(rfm_segment_v2);
CREATE INDEX idx_cltv_segment ON kiran.tbl_customer_profile(cltv_segment);
CREATE INDEX idx_churn_segment ON kiran.tbl_customer_profile(churn_segment);
CREATE INDEX idx_update_date ON kiran.tbl_customer_profile(update_date);

-- Run maintenance
VACUUM kiran.tbl_customer_profile;
ANALYZE kiran.tbl_customer_profile;
```

**Alternative**: Upgrade to Vercel Pro ($20/month) for 60-second timeout

---

### 🔴 Issue 5: GitHub Push Fails - "Authentication failed"

**Symptoms**:
- `git push` fails with: `fatal: Authentication failed`
- GitHub asks for password

**Cause**: GitHub requires personal access token, not password

**Fix - Create GitHub Token**:

1. Go to: https://github.com/settings/tokens
2. Click: **Generate new token (classic)**
3. Name: `vercel-dashboard-deploy`
4. Expiration: `90 days`
5. Scopes: Check ✅ **repo** (all sub-items)
6. Click: **Generate token**
7. **COPY TOKEN** (shown once only!)

8. Configure git to use token:
```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Option A: Store in git config
git config credential.helper store
git push origin main
# When prompted:
# Username: kiran-EA
# Password: [paste token here]

# Option B: Use token in URL
git remote set-url origin https://[TOKEN]@github.com/kiran-EA/lampsplus-customer-dashboard.git
git push origin main
```

---

### 🔴 Issue 6: Vercel Can't Find GitHub Repository

**Symptoms**:
- Vercel import page doesn't show your repo
- "No repositories found" message

**Cause**: Vercel not authorized to access your GitHub account

**Fix - Authorize Vercel**:

1. Go to: https://vercel.com/dashboard
2. Click your avatar → **Settings**
3. Click: **Git Integration**
4. Click: **Connect GitHub Account**
5. Authorize Vercel to access `kiran-EA` organization
6. Select: `All repositories` or `Only select repositories`
7. Save

8. Retry import:
   - Dashboard → **Add New** → **Project**
   - Should now see `lampsplus-customer-dashboard`

---

### 🔴 Issue 7: Local Testing Fails - "Module not found"

**Symptoms**:
- Running `python local_dev.py` fails
- Error: `ModuleNotFoundError: No module named 'flask'`

**Cause**: Dependencies not installed locally

**Fix**:
```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Install dependencies
pip install -r requirements.txt --user

# If pip install fails, try with --break-system-packages
pip install -r requirements.txt --break-system-packages

# Verify installation
python -c "import flask; import redshift_connector; import pandas; print('✅ All modules imported')"

# Try again
python local_dev.py
```

---

### 🔴 Issue 8: Dashboard Shows Old Data or Wrong Row Count

**Symptoms**:
- Dashboard shows data but numbers seem wrong
- Row counts don't match pipeline output

**Cause**: Dashboard is querying live but pipeline wrote to different table

**Fix - Verify Table Name**:

```bash
# Check what table the dashboard is querying
grep "TABLE =" /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel/api/index.py

# Should show: TABLE = "KIRAN.TBL_CUSTOMER_PROFILE"

# Verify this matches your pipeline
grep "FINAL_TABLE" /home/devmgr/KiranDev/customer_profile/rfm_cltv_tbl_customer_profile.py

# If different, update api/index.py:
nano /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel/api/index.py
# Change TABLE = "KIRAN.TBL_CUSTOMER_PROFILE" to match pipeline

git add api/index.py
git commit -m "Fix: Update table name"
git push origin main
```

---

### 🔴 Issue 9: CORS Error in Browser Console

**Symptoms**:
- Browser console shows: `CORS policy blocked`
- API calls fail with CORS error

**Cause**: Missing CORS headers (rare on Vercel, but possible)

**Fix - Add CORS to Flask**:

```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Update requirements.txt
echo "flask-cors==4.0.0" >> requirements.txt

# Update api/index.py - add after imports
nano api/index.py
```

Add these lines after `app = Flask(__name__)`:

```python
from flask_cors import CORS
CORS(app, origins=["https://your-app.vercel.app", "http://localhost:5050"])
```

```bash
git add requirements.txt api/index.py
git commit -m "Fix: Add CORS support"
git push origin main
```

---

### 🔴 Issue 10: HTML Loads But Charts Don't Render

**Symptoms**:
- Dashboard skeleton appears
- No charts or graphs
- Browser console shows: `Chart is not defined`

**Cause**: Chart.js CDN blocked or slow to load

**Fix - Verify CDN in HTML**:

```bash
# Check Chart.js CDN link in HTML
grep "chart.js" /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel/public/index.html

# Should show:
# <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

# If missing or wrong version, update:
nano /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel/public/index.html

# Find <head> section and add:
# <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

git add public/index.html
git commit -m "Fix: Add Chart.js CDN"
git push origin main
```

---

## 🔍 How to Find Error Messages

### Vercel Build Logs

1. Go to: https://vercel.com/dashboard
2. Click your project
3. Click: **Deployments** tab
4. Click on the latest deployment (should show ❌ red X if failed)
5. Scroll down to **Build Logs** section
6. Look for red error messages
7. Copy the error and search this guide

### Vercel Function Logs (Runtime Errors)

1. Go to: https://vercel.com/dashboard
2. Click your project
3. Click: **Deployments** tab
4. Click on latest deployment
5. Click: **Function Logs** tab
6. Look for errors when you make API calls
7. Copy error stack trace

### Browser Console Logs

1. Open dashboard in browser
2. Press `F12` (or right-click → Inspect)
3. Click: **Console** tab
4. Look for red errors
5. Click: **Network** tab
6. Refresh page
7. Click on any red/failed requests
8. Check **Response** tab for error details

---

## 🚨 Emergency Fixes

### Nuclear Option: Start Fresh

If nothing works, start over with clean setup:

```bash
# On gpu01
cd /home/devmgr/KiranDev/customer_profile
rm -rf customer-dashboard-vercel

# Download files from Claude again (or from backup)
tar -xzf customer-dashboard-vercel.tar.gz
cd customer-dashboard-vercel

# Verify all files present
ls -la
# Should see: api/, public/, vercel.json, requirements.txt, etc.

# Delete old GitHub repo
gh repo delete kiran-EA/lampsplus-customer-dashboard --yes

# Create new repo
git init
git add .
git commit -m "Fresh start: Customer dashboard"
gh repo create lampsplus-customer-dashboard --private --source=. --remote=origin --push

# Delete old Vercel project
# Go to: https://vercel.com/dashboard
# Click project → Settings → scroll to bottom → Delete Project

# Re-import to Vercel
# Dashboard → Add New → Project → Import from GitHub
# Select: lampsplus-customer-dashboard
# Add environment variables (REDSHIFT_HOST, etc.)
# Deploy
```

---

## 📞 Still Stuck?

If none of these fixes work:

1. **Paste error message**: Show me the exact error from Vercel logs
2. **Share deployment URL**: What URL did Vercel assign?
3. **Check Redshift access**: Can you query Redshift from gpu01?

```bash
# Test Redshift connection from gpu01
python3 << 'EOF'
import redshift_connector
try:
    conn = redshift_connector.connect(
        host='ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com',
        port=5439,
        database='express',
        user='easuper',
        password='LAMRedPWD@2024'
    )
    print("✅ Redshift connection successful")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM kiran.tbl_customer_profile")
    print(f"✅ Row count: {cursor.fetchone()[0]:,}")
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
EOF
```

Share the output and I'll help debug further!

---

## ✅ Success Checklist

Once fixed, verify these all work:

- [ ] Dashboard loads: `https://your-app.vercel.app/`
- [ ] API health check: `https://your-app.vercel.app/api/health`
- [ ] API summary returns data: `https://your-app.vercel.app/api/summary`
- [ ] All 8 pages render (Overview, Pipeline Health, etc.)
- [ ] Charts display correctly
- [ ] Segment drill-downs work
- [ ] CSV download works
- [ ] Year filter changes data

If all checked ✅ → **You're live!** 🎉
