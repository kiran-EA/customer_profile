# ⚡ Quick Deployment Checklist

Follow these steps in order to deploy your dashboard to Vercel in ~10 minutes.

---

## ✅ Step 1: Test Locally (Optional but Recommended)

```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Install dependencies
pip install -r requirements.txt python-dotenv

# Create .env file
cp .env.example .env
# (Edit .env if needed - defaults are already correct)

# Test locally
python local_dev.py

# Open browser: http://192.168.1.42:5050
# Verify all pages load and data appears
# Press Ctrl+C to stop
```

---

## ✅ Step 2: Push to GitHub

```bash
cd /home/devmgr/KiranDev/customer_profile/customer-dashboard-vercel

# Initialize git
git init
git add .
git commit -m "Initial commit: LampsPlus Customer Dashboard"

# Create GitHub repo (Option A: via GitHub CLI)
gh repo create lampsplus-customer-dashboard --private --source=. --remote=origin --push

# OR (Option B: via web)
# 1. Go to: https://github.com/new
# 2. Repo name: lampsplus-customer-dashboard
# 3. Set Private
# 4. Click "Create repository"
# Then run:
git remote add origin https://github.com/kiran-EA/lampsplus-customer-dashboard.git
git branch -M main
git push -u origin main
```

---

## ✅ Step 3: Deploy to Vercel

### 3.1: Import Project
1. Go to: https://vercel.com/dashboard
2. Click: **"Add New..."** → **"Project"**
3. Click: **"Import Git Repository"**
4. Select: **kiran-EA/lampsplus-customer-dashboard**
5. Click: **"Import"**

### 3.2: Configure Build Settings
Leave all defaults as-is:
- Framework Preset: **Other**
- Root Directory: `./`
- Build Command: (empty)
- Output Directory: `public`
- Install Command: `pip install -r requirements.txt`

### 3.3: Add Environment Variables ⚠️ CRITICAL
Click **"Environment Variables"** tab and add these **EXACTLY**:

| Name | Value |
|------|-------|
| `REDSHIFT_HOST` | `ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com` |
| `REDSHIFT_PORT` | `5439` |
| `REDSHIFT_DATABASE` | `express` |
| `REDSHIFT_USER` | `easuper` |
| `REDSHIFT_PASSWORD` | `LAMRedPWD@2024` |

**Important**: Check all 3 environments (Production, Preview, Development)

### 3.4: Deploy
1. Click **"Deploy"**
2. Wait 2-3 minutes (watch build logs)
3. Look for: ✅ **"Build Completed"**
4. Click: **"Visit"** button

---

## ✅ Step 4: Verify Deployment

### Test these endpoints:
1. **Dashboard home**: `https://your-app.vercel.app/`
2. **Health check**: `https://your-app.vercel.app/api/health`
3. **Summary data**: `https://your-app.vercel.app/api/summary`

### Verify all 8 pages load:
- [x] Overview
- [x] Pipeline Health
- [x] QC Status
- [x] Segments
- [x] Predictions
- [x] Top Customers
- [x] Data Lineage
- [x] Samples + Download

### Test features:
- [x] KPI cards show numbers
- [x] Charts render correctly
- [x] Segment drill-down works
- [x] CSV download works
- [x] Year filter changes data

---

## ✅ Step 5: Share & Secure

### Get your URL:
```
https://lampsplus-customer-dashboard-xxx.vercel.app
```

### Copy from Vercel dashboard → "Domains" tab

### Share with team:
- Internal stakeholders
- Marketing team
- Data analysts

### (Optional) Add password protection:
See README.md → "Security Best Practices" section

---

## 🎉 Success!

Your dashboard is now live with:
- ✅ Real-time Redshift data
- ✅ 15.3M customer profiles
- ✅ RFM segmentation
- ✅ CLTV predictions
- ✅ Churn risk analysis
- ✅ Downloadable CSVs

---

## 🔄 Future Updates

Every time you `git push`, Vercel auto-deploys:

```bash
# Make changes
nano api/index.py

# Commit and push
git add .
git commit -m "Update: Add new feature"
git push origin main

# Vercel auto-deploys in 1-2 minutes
```

---

## 📞 Troubleshooting

**Issue**: Dashboard loads but no data
- Check Vercel logs: Dashboard → Deployments → Latest → "Function Logs"
- Verify environment variables are set correctly
- Test Redshift connection from gpu01

**Issue**: API returns 500 error
- Check Function Logs for Python errors
- Verify Redshift credentials
- Check table permissions

**Issue**: Slow first load
- Normal! Serverless cold start + Redshift connection (~2-3 seconds)
- Subsequent loads are fast (~500ms)

---

## 📚 Documentation

- **Full guide**: README.md
- **API docs**: README.md → "API Endpoints"
- **Security**: README.md → "Security Best Practices"
- **Pipeline integration**: README.md → "Data Pipeline Integration"

---

**Total time**: ~10 minutes  
**Cost**: $0 (Vercel Hobby plan)  
**Data freshness**: Live (queries on every request)  

🚀 **Your live dashboard is ready!**
