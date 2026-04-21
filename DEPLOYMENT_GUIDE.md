# 🚀 Production Deployment Guide: Vercel + Railway

This guide will take GridMint from local development to production deployment using:
- **Vercel** → React frontend (static site)
- **Railway** → FastAPI backend (Python API + WebSocket)

**Estimated Time**: 30-45 minutes  
**Prerequisites**: GitHub account, Vercel account, Railway account, Gemini API key

---

## 📋 Phase 1: Pre-Deployment Preparation

### 1.1 Verify Local Build Success

Before deploying, ensure everything works locally:

```bash
# Test backend build
cd /Users/taylanbal/Desktop/arc-hackathon/gridmint
source .venv/bin/activate
python -c "from engine.orchestrator import app; print('✅ Backend imports OK')"

# Test frontend build
cd frontend
npm install
npm run build
# Should output: dist/ directory created successfully
```

**Critical Check**: If either test fails, fix errors before proceeding.

---

### 1.2 Environment Variables Audit

You'll need these values ready (from your `.env` file):

**Required for Backend (Railway)**:
```bash
# Gemini AI (CRITICAL - get from https://aistudio.google.com/app/apikey)
GEMINI_API_KEY=your_actual_gemini_key_here

# Arc Testnet (pre-configured, no changes needed)
ARC_RPC_URL=https://rpc.testnet.arc.network
ARC_CHAIN_ID=5042002
USDC_CONTRACT_ADDRESS=0x3600000000000000000000000000000000000000

# Settlement Mode
SETTLEMENT_MODE=live  # or "simulated" for demo mode

# Agent Private Keys (10 wallets - from scripts/setup_wallets.py)
SOLAR_1_PRIVATE_KEY=0x...
SOLAR_2_PRIVATE_KEY=0x...
SOLAR_3_PRIVATE_KEY=0x...
CONSUMER_1_PRIVATE_KEY=0x...
CONSUMER_2_PRIVATE_KEY=0x...
CONSUMER_3_PRIVATE_KEY=0x...
CONSUMER_4_PRIVATE_KEY=0x...
CONSUMER_5_PRIVATE_KEY=0x...
BATTERY_1_PRIVATE_KEY=0x...
BATTERY_2_PRIVATE_KEY=0x...

# Circle (optional - leave blank to use direct ERC-20)
CIRCLE_API_KEY=  # Leave empty for Arc direct settlement
CIRCLE_SETTLEMENT_BACKEND=erc20
```

**Frontend (Vercel)**: No environment variables needed initially (will update API URL after Railway deployment).

---

### 1.3 Create Production Configuration Files

We need to make the frontend API URL configurable and add Railway deployment config.

#### A. Create Railway Configuration

```bash
# Create railway.json in project root
cd /Users/taylanbal/Desktop/arc-hackathon/gridmint
cat > railway.json << 'EOF'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "pip install -r requirements.txt"
  },
  "deploy": {
    "startCommand": "uvicorn engine.orchestrator:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
EOF
```

#### B. Update Frontend to Use Environment Variable for API URL

We need to make the API URL configurable (currently hardcoded to localhost:8000).

---

## 🏗️ Phase 2: Backend Deployment (Railway)

### 2.1 Connect GitHub Repository to Railway

1. Go to **https://railway.app**
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Authenticate with GitHub
5. Select repository: **`midasbal/GridMint`**
6. Railway will auto-detect Python and start building

### 2.2 Configure Environment Variables

In Railway dashboard:

1. Click your project → **"Variables"** tab
2. Click **"New Variable"** and add ALL variables from section 1.2 above
3. **CRITICAL**: Use **"Raw Editor"** mode for batch paste:

```bash
GEMINI_API_KEY=your_actual_key_here
ARC_RPC_URL=https://rpc.testnet.arc.network
ARC_CHAIN_ID=5042002
USDC_CONTRACT_ADDRESS=0x3600000000000000000000000000000000000000
SETTLEMENT_MODE=live
SOLAR_1_PRIVATE_KEY=0x...
SOLAR_2_PRIVATE_KEY=0x...
# ... (paste all 10 agent keys)
```

4. Click **"Save Variables"** → Railway will auto-redeploy

### 2.3 Verify Deployment

1. Wait for build to complete (~3-5 minutes)
2. Railway will assign a URL like: `https://gridmint-production.up.railway.app`
3. Test endpoints:
   ```bash
   # Health check
   curl https://gridmint-production.up.railway.app/api/status
   
   # Should return JSON with grid_state, tick_count, etc.
   ```

4. **If deployment fails**, check logs:
   - Railway dashboard → **"Deployments"** → Click latest → **"View Logs"**
   - Common issues:
     - Missing environment variables (Railway will show `KeyError`)
     - Python version mismatch (Railway uses Python 3.11+ by default)
     - Dependency conflicts (check `requirements.txt`)

### 2.4 Configure CORS for Production

**⚠️ CRITICAL SECURITY STEP**:

After Railway deployment, you must update CORS to allow your Vercel domain.

**We'll do this in Phase 3.3** after getting the Vercel URL.

---

## 🎨 Phase 3: Frontend Deployment (Vercel)

### 3.1 Update Frontend API Configuration

Before deploying to Vercel, we need to make the API URL environment-aware.

**Option A: Use Vite Environment Variables (Recommended)**

1. Create `frontend/.env.production`:
   ```bash
   cd /Users/taylanbal/Desktop/arc-hackathon/gridmint/frontend
   cat > .env.production << 'EOF'
   VITE_API_URL=https://gridmint-production.up.railway.app
   EOF
   ```

2. Update `frontend/src/pages/Dashboard.tsx` to use environment variable:
   ```typescript
   // Line 8 - Replace:
   const API = 'http://localhost:8000'
   
   // With:
   const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
   
   // Line 334 - Replace WebSocket URL:
   ws = new WebSocket('ws://localhost:8000/ws')
   
   // With:
   const wsUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace('http', 'ws')
   ws = new WebSocket(`${wsUrl}/ws`)
   ```

3. Commit changes:
   ```bash
   git add frontend/.env.production frontend/src/pages/Dashboard.tsx
   git commit -m "Configure production API URL for Vercel deployment"
   git push
   ```

**Option B: Hardcode Railway URL (Quick & Dirty)**

If you want to deploy immediately without environment variables:

1. Edit `frontend/src/pages/Dashboard.tsx`:
   ```typescript
   // Line 8 - Replace with your Railway URL:
   const API = 'https://gridmint-production.up.railway.app'
   
   // Line 334:
   ws = new WebSocket('wss://gridmint-production.up.railway.app/ws')
   ```

2. Commit and push:
   ```bash
   git add frontend/src/pages/Dashboard.tsx
   git commit -m "Update API URL for production"
   git push
   ```

### 3.2 Deploy to Vercel

1. Go to **https://vercel.com**
2. Click **"New Project"**
3. Import **`midasbal/GridMint`** from GitHub
4. **Configure Project**:
   - **Framework Preset**: Vite
   - **Root Directory**: `frontend/`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
   - **Install Command**: `npm install`

5. **Environment Variables** (if using Option A):
   - Click **"Environment Variables"**
   - Add: `VITE_API_URL` = `https://gridmint-production.up.railway.app`

6. Click **"Deploy"**

### 3.3 Update CORS in Backend

After Vercel deployment completes, you'll get a URL like:
```
https://gridmint.vercel.app
```

**Now update Railway CORS settings**:

1. In your local repository, edit `engine/orchestrator.py`:
   ```python
   # Lines 508-514 - Add your Vercel domain:
   app.add_middleware(
       CORSMiddleware,
       allow_origins=[
           "http://localhost:5173",
           "http://127.0.0.1:5173",
           "https://gridmint.vercel.app",  # ← Add this
           "https://*.vercel.app",          # ← Allow preview deploys
       ],
       allow_credentials=False,
       allow_methods=["GET", "POST"],
       allow_headers=["Content-Type", "X-Payment", "X-Payment-Proof"],
   )
   ```

2. Commit and push:
   ```bash
   git add engine/orchestrator.py
   git commit -m "Add Vercel domain to CORS whitelist"
   git push
   ```

3. Railway will auto-redeploy (takes ~2 minutes)

### 3.4 Verify Production Deployment

1. Visit `https://gridmint.vercel.app`
2. Test all pages:
   - **Landing page** (`/`) → Should load instantly
   - **Dashboard** (`/dashboard`) → Should connect to WebSocket and show live data
   - **Whitepaper** (`/whitepaper`) → Should load with correct stats (264 txs)

3. **Open browser DevTools** → Console tab:
   - ✅ No CORS errors
   - ✅ WebSocket connected successfully
   - ✅ API calls returning data

4. **Test WebSocket streaming**:
   - Dashboard should show real-time price updates every 3 seconds
   - Transactions should appear in the feed
   - Agent balances should update live

---

## 🚨 Critical Configuration Checklist

### Backend (Railway)

- [ ] ✅ All 10+ environment variables configured
- [ ] ✅ `GEMINI_API_KEY` is valid (test with curl)
- [ ] ✅ Agent wallets funded with testnet USDC
- [ ] ✅ CORS includes Vercel domain
- [ ] ✅ Port is `$PORT` (Railway auto-assigns)
- [ ] ✅ Health endpoint responds: `/api/status`

### Frontend (Vercel)

- [ ] ✅ Build succeeds with `npm run build`
- [ ] ✅ API URL points to Railway domain
- [ ] ✅ WebSocket URL uses `wss://` (not `ws://`)
- [ ] ✅ All routes work (/, /dashboard, /whitepaper)
- [ ] ✅ No console errors in DevTools

### Security

- [ ] ✅ `.env` file NOT committed to Git (check `.gitignore`)
- [ ] ✅ Private keys only in Railway environment variables
- [ ] ✅ CORS restricted to specific domains (not `*`)
- [ ] ✅ No API keys in frontend code (check with `grep -r "GEMINI" frontend/src/`)

---

## 🐛 Common Issues & Solutions

### Issue 1: CORS Error on Dashboard

**Symptom**: 
```
Access to XMLHttpRequest at 'https://gridmint-production.up.railway.app/api/status' 
from origin 'https://gridmint.vercel.app' has been blocked by CORS policy
```

**Solution**:
1. Check `engine/orchestrator.py` line 508-514
2. Ensure your Vercel domain is in `allow_origins` list
3. Push changes to trigger Railway redeploy
4. Hard refresh browser (Cmd+Shift+R / Ctrl+F5)

---

### Issue 2: WebSocket Connection Failed

**Symptom**: 
```
WebSocket connection to 'ws://gridmint-production.up.railway.app/ws' failed
```

**Solution**:
1. Change `ws://` to `wss://` (secure WebSocket)
2. Railway requires HTTPS/WSS for all connections
3. Update `Dashboard.tsx` line 334:
   ```typescript
   ws = new WebSocket('wss://gridmint-production.up.railway.app/ws')
   ```

---

### Issue 3: Railway Build Fails

**Symptom**: 
```
ERROR: Could not find a version that satisfies the requirement google-genai>=1.0.0
```

**Solution**:
1. Check Python version (Railway uses 3.11+)
2. Update `requirements.txt` to pin versions:
   ```
   google-generativeai==0.8.0  # Instead of google-genai>=1.0.0
   ```
3. Push changes to trigger rebuild

---

### Issue 4: Gemini API Rate Limit

**Symptom**: Backend logs show:
```
429 Too Many Requests: Resource has been exhausted
```

**Solution**:
1. Gemini free tier: 15 RPM (requests per minute)
2. Battery agents call Gemini every 5th tick (~1 request/15 seconds)
3. With 2 batteries = 8 requests/minute (within limit)
4. If rate limited:
   - Reduce simulation speed (increase tick duration)
   - Or upgrade to Gemini Pro API tier
   - Or set `SETTLEMENT_MODE=simulated` to disable live trading

---

### Issue 5: Agent Wallets Underfunded

**Symptom**: 
```
Transaction failed: insufficient funds for transfer
```

**Solution**:
1. Fund all 10 agent wallets with testnet USDC
2. Use Circle Faucet: https://faucet.circle.com
3. Select **"Arc Testnet"** network
4. Request 10 USDC per wallet
5. Each wallet address from `scripts/setup_wallets.py` output

---

## 🔍 Monitoring & Health Checks

### Railway Logs

Monitor backend in real-time:
```bash
# Via Railway CLI (install: npm i -g @railway/cli)
railway logs --service backend

# Or use Railway dashboard: Deployments → View Logs
```

**What to look for**:
- `✅ GridEngine initialized with 10 agents`
- `🔴 LIVE MODE: Using GatewaySettler`
- `WebSocket /ws: Dashboard connected`
- `Trade executed: solar-1 → consumer-2 (0.05 kWh @ $0.004)`

### Vercel Analytics

Track frontend performance:
1. Vercel dashboard → Your project → **"Analytics"**
2. Check:
   - Page load times (<1s for landing, <2s for dashboard)
   - Web Vitals (should be green)
   - Error rate (<1%)

### Health Check Endpoints

**Backend**:
```bash
# Grid status
curl https://gridmint-production.up.railway.app/api/status

# Agent list
curl https://gridmint-production.up.railway.app/api/agents

# Payment stats
curl https://gridmint-production.up.railway.app/api/payments
```

**Frontend**:
```bash
# Should return 200 OK
curl -I https://gridmint.vercel.app

# Test routing
curl -I https://gridmint.vercel.app/dashboard
curl -I https://gridmint.vercel.app/whitepaper
```

---

## 🎯 Post-Deployment Tasks

### 1. Update Repository URLs

Update `README.md` and `presentation.md` with live URLs:

```bash
cd /Users/taylanbal/Desktop/arc-hackathon/gridmint

# Edit README.md line 14-15:
# [Live Dashboard](https://gridmint.vercel.app/dashboard)
# [Whitepaper](https://gridmint.vercel.app/whitepaper)
# [API Docs](https://gridmint-production.up.railway.app/docs)

# Edit presentation.md line 255-256:
# **Project GitHub**: https://github.com/midasbal/GridMint
# **Live Demo**: https://gridmint.vercel.app/dashboard
# **API Backend**: https://gridmint-production.up.railway.app/docs

git add README.md presentation.md
git commit -m "Update documentation with production URLs"
git push
```

### 2. Test from External Network

Use a different device or mobile phone to verify:
- Dashboard loads and updates in real-time
- No authentication errors
- WebSocket streams data continuously
- All images and assets load

### 3. Performance Optimization (Optional)

**Vercel**:
- Enable **Edge Caching** for static assets
- Configure **Image Optimization** for logo/icons
- Set up **Custom Domain** (e.g., gridmint.io)

**Railway**:
- Upgrade to **Pro Plan** for 8GB RAM (free tier: 512MB)
- Enable **Healthchecks** to auto-restart on failures
- Add **Custom Domain** for API (e.g., api.gridmint.io)

### 4. Set Up Monitoring Alerts

**Railway**:
1. Go to project → **"Settings"** → **"Notifications"**
2. Enable:
   - Deployment failures
   - High memory usage (>80%)
   - Crash loop detection

**Vercel**:
1. Project → **"Settings"** → **"Notifications"**
2. Enable:
   - Build failures
   - Domain SSL issues

---

## 📊 Final Verification Matrix

Before marking deployment as complete, verify:

| Component | Checkpoint | Status |
|-----------|------------|--------|
| **Railway Backend** | `/api/status` returns 200 OK | [ ] |
| | `/docs` shows Swagger UI | [ ] |
| | WebSocket `/ws` accepts connections | [ ] |
| | Logs show no errors | [ ] |
| **Vercel Frontend** | Landing page loads <1s | [ ] |
| | Dashboard connects to WebSocket | [ ] |
| | No CORS errors in console | [ ] |
| | All routes work (/, /dashboard, /whitepaper) | [ ] |
| **Integration** | Real-time price updates appear | [ ] |
| | Transactions stream to dashboard | [ ] |
| | Agent balances update correctly | [ ] |
| | Gemini AI decisions logged | [ ] |
| **Security** | No private keys in frontend | [ ] |
| | CORS restricted to Vercel domain | [ ] |
| | Railway environment variables secure | [ ] |
| **Documentation** | README.md has production URLs | [ ] |
| | presentation.md updated | [ ] |
| | DEPLOYMENT_GUIDE.md exists | [ ] |

---

## 🎉 Success Criteria

Your deployment is successful when:

1. ✅ **Frontend**: `https://gridmint.vercel.app` loads all pages without errors
2. ✅ **Backend**: `https://gridmint-production.up.railway.app/docs` shows API documentation
3. ✅ **Real-Time**: Dashboard displays live grid data streaming via WebSocket
4. ✅ **Transactions**: On-chain USDC settlements appear in logs
5. ✅ **AI**: Gemini battery decisions visible in `/api/agents` endpoint
6. ✅ **Performance**: Page load <2s, WebSocket latency <100ms
7. ✅ **No Errors**: Zero CORS issues, zero console errors, zero 500 responses

---

## 📞 Troubleshooting Contact

If deployment fails after following this guide:

1. **Check Railway logs** for backend errors
2. **Check Vercel logs** for build failures
3. **Check browser DevTools console** for frontend errors
4. **Verify environment variables** are correctly set
5. **Test locally first** to isolate issues

**Common mistakes**:
- Forgetting to update CORS in `orchestrator.py`
- Using `ws://` instead of `wss://` for WebSocket
- Missing Gemini API key or invalid key
- Agent wallets not funded with testnet USDC
- Frontend still pointing to `localhost:8000`

---

## 🚀 Next Steps After Deployment

1. **Generate Slide Deck**: Use `presentation.md` prompt with Gemini/NotebookLM
2. **Record Video**: Follow `VIDEO_SCRIPT.md` (Scene 1-10, 5 minutes)
3. **Take Screenshot**: Capture dashboard at 1920×1080 for cover image
4. **Submit to Hackathon**: Upload all materials to Circle x Arc portal
5. **Write Product Feedback**: Complete Circle feedback form (500+ words)

---

**Deployment Guide Version**: 1.0  
**Last Updated**: 22 April 2026  
**Tested On**: Vercel v2024, Railway v2024, Python 3.11, Node.js 20

**Good luck with your deployment! 🎯**
