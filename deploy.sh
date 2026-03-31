#!/bin/bash
# ==============================================================================
# LampsPlus Customer Dashboard - Automated Vercel Deployment
# ==============================================================================
# This script automates the deployment process from gpu01 to Vercel
# Run: bash deploy.sh
# ==============================================================================

set -e  # Exit on any error

echo "════════════════════════════════════════════════════════════════"
echo "  LampsPlus Customer Dashboard - Vercel Deployment Wizard"
echo "════════════════════════════════════════════════════════════════"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running from correct directory
if [ ! -f "vercel.json" ]; then
    echo -e "${RED}❌ Error: vercel.json not found${NC}"
    echo "Please run this script from the customer-dashboard-vercel directory"
    exit 1
fi

echo -e "${GREEN}✅ Step 1/6: Verify project files${NC}"
echo "Checking required files..."

required_files=("api/index.py" "public/index.html" "requirements.txt" "vercel.json" "runtime.txt")
for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo -e "  ${RED}✗ Missing: $file${NC}"
        exit 1
    fi
done
echo ""

echo -e "${GREEN}✅ Step 2/6: Initialize Git repository${NC}"
if [ -d ".git" ]; then
    echo "  ℹ Git repository already initialized"
else
    git init
    echo "  ✓ Git repository initialized"
fi
echo ""

echo -e "${GREEN}✅ Step 3/6: Stage files for commit${NC}"
git add .
echo "  ✓ All files staged"
echo ""

echo -e "${GREEN}✅ Step 4/6: Create commit${NC}"
if git diff --cached --quiet; then
    echo "  ℹ No changes to commit"
else
    git commit -m "Deploy: LampsPlus Customer Dashboard to Vercel"
    echo "  ✓ Changes committed"
fi
echo ""

echo -e "${YELLOW}⚠️  Step 5/6: GitHub Repository Setup${NC}"
echo ""
echo "You need to create a GitHub repository. Choose one option:"
echo ""
echo "  ${BLUE}Option A: Using GitHub CLI (gh)${NC}"
echo "  Command: gh repo create lampsplus-customer-dashboard --private --source=. --remote=origin --push"
echo ""
echo "  ${BLUE}Option B: Using GitHub Web UI${NC}"
echo "  1. Go to: https://github.com/new"
echo "  2. Repository name: lampsplus-customer-dashboard"
echo "  3. Set to Private"
echo "  4. Do NOT initialize with README"
echo "  5. Click 'Create repository'"
echo "  6. Then run:"
echo "     git remote add origin https://github.com/kiran-EA/lampsplus-customer-dashboard.git"
echo "     git branch -M main"
echo "     git push -u origin main"
echo ""

read -p "Have you created the GitHub repository? (y/n): " github_done
if [[ ! "$github_done" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⏸ Paused - Create GitHub repository then re-run this script${NC}"
    exit 0
fi

# Check if remote exists
if git remote get-url origin &>/dev/null; then
    echo "  ✓ Git remote configured"
    
    # Try to push
    echo "  → Pushing to GitHub..."
    if git push -u origin main 2>&1; then
        echo -e "  ${GREEN}✓ Pushed to GitHub successfully${NC}"
    else
        echo -e "  ${YELLOW}⚠️  Push failed - you may need to authenticate${NC}"
        echo "  If authentication failed, create a personal access token:"
        echo "  1. Go to: https://github.com/settings/tokens"
        echo "  2. Generate new token (classic)"
        echo "  3. Select 'repo' scope"
        echo "  4. Use token as password when git asks"
    fi
else
    echo -e "  ${YELLOW}⚠️  No git remote configured${NC}"
    echo "  Run: git remote add origin https://github.com/kiran-EA/lampsplus-customer-dashboard.git"
    exit 1
fi
echo ""

echo -e "${GREEN}✅ Step 6/6: Vercel Deployment Instructions${NC}"
echo ""
echo "Your code is now on GitHub! Next steps:"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ${BLUE}VERCEL DEPLOYMENT (Web UI)${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "1. Go to: ${BLUE}https://vercel.com/dashboard${NC}"
echo ""
echo "2. Click: ${GREEN}'Add New...'${NC} → ${GREEN}'Project'${NC}"
echo ""
echo "3. Click: ${GREEN}'Import Git Repository'${NC}"
echo ""
echo "4. Select: ${GREEN}kiran-EA/lampsplus-customer-dashboard${NC}"
echo "   (If not visible, click 'Configure GitHub App' and authorize)"
echo ""
echo "5. Click: ${GREEN}'Import'${NC}"
echo ""
echo "6. ${RED}CRITICAL${NC} - Add Environment Variables:"
echo "   Click 'Environment Variables' tab and add these:"
echo ""
echo "   ${YELLOW}Name${NC}                  ${YELLOW}Value${NC}"
echo "   ──────────────────── ────────────────────────────────────────────"
echo "   REDSHIFT_HOST        ea-non-prod.cxw4zfxatj9b.us-west-1.redshift.amazonaws.com"
echo "   REDSHIFT_PORT        5439"
echo "   REDSHIFT_DATABASE    express"
echo "   REDSHIFT_USER        easuper"
echo "   REDSHIFT_PASSWORD    LAMRedPWD@2024"
echo ""
echo "   ${RED}⚠️  Check all 3 boxes: Production, Preview, Development${NC}"
echo ""
echo "7. Click: ${GREEN}'Deploy'${NC}"
echo ""
echo "8. Wait 2-3 minutes for build to complete"
echo ""
echo "9. Click: ${GREEN}'Visit'${NC} to open your live dashboard!"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Your dashboard will be live at:"
echo "  ${GREEN}https://lampsplus-customer-dashboard-[random].vercel.app${NC}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  ${BLUE}Troubleshooting${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "If deployment fails:"
echo "  • Check build logs in Vercel dashboard"
echo "  • Verify all 5 environment variables are set"
echo "  • See TROUBLESHOOTING.md for common issues"
echo ""
echo "GitHub repo URL:"
echo "  ${BLUE}https://github.com/kiran-EA/lampsplus-customer-dashboard${NC}"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "${GREEN}🎉 Git setup complete! Follow Vercel steps above.${NC}"
echo "═══════════════════════════════════════════════════════════════"
