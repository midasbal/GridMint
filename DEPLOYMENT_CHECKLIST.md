# 🚀 Quick Deployment Checklist

## Prerequisites
- [x] GitHub repository created: https://github.com/midasbal/GridMint
- [x] Deployment guide created: `DEPLOYMENT_GUIDE.md`
- [x] Code pushed to GitHub with deployment configuration

## Phase 1: Backend (Railway) - 15 minutes

### Steps:
1. **Go to Railway**: https://railway.app
2. **New Project** → **Deploy from GitHub** → Select `midasbal/GridMint`
3. **Add Environment Variables** (Variables tab → Raw Editor):
   ```bash
   GEMINI_API_KEY=your_actual_key_here
   ARC_RPC_URL=https://rpc.testnet.arc.network
   ARC_CHAIN_ID=5042002
   USDC_CONTRACT_ADDRESS=0x3600000000000000000000000000000000000000
   SETTLEMENT_MODE=live
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
   ```
4. **Wait for deployment** (~3-5 minutes)
5. **Copy Railway URL**: e.g., `https://gridmint-production.up.railway.app`
6. **Test**: `curl https://your-railway-url.up.railway.app/api/status`

## Phase 2: Frontend (Vercel) - 10 minutes

### Steps:
1. **Update API URL**: Edit `frontend/.env.production`
   ```bash
   VITE_API_URL=https://your-railway-url.up.railway.app
   ```

2. **Commit and push**:
   ```bash
   git add frontend/.env.production
   git commit -m "Update production API URL"
   git push
   ```

3. **Go to Vercel**: https://vercel.com
4. **New Project** → Import `midasbal/GridMint`
5. **Configure**:
   - Framework: Vite
   - Root Directory: `frontend/`
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Environment Variable: `VITE_API_URL` = Your Railway URL

6. **Deploy** → Wait 2-3 minutes
7. **Copy Vercel URL**: e.g., `https://gridmint.vercel.app`

## Phase 3: Update CORS - 5 minutes

### Steps:
1. **Edit** `engine/orchestrator.py` line 510:
   ```python
   "https://gridmint.vercel.app",  # Your actual Vercel domain
   ```

2. **Commit and push**:
   ```bash
   git add engine/orchestrator.py
   git commit -m "Add Vercel domain to CORS"
   git push
   ```

3. **Railway auto-redeploys** (~2 minutes)

## Phase 4: Verification - 5 minutes

### Test Checklist:
- [ ] Visit `https://your-vercel-url.vercel.app`
- [ ] Dashboard loads without CORS errors
- [ ] WebSocket connects (real-time updates appear)
- [ ] All API calls succeed (check DevTools Network tab)
- [ ] Transactions appear in trade feed
- [ ] Agent balances update in real-time

### Quick Tests:
```bash
# Backend health
curl https://your-railway-url.up.railway.app/api/status

# Frontend health
curl -I https://your-vercel-url.vercel.app
```

## Critical Configuration

### Backend Environment Variables (Railway)
**Required**:
- `GEMINI_API_KEY` - Get from https://aistudio.google.com/app/apikey
- `SETTLEMENT_MODE` - Set to `live` or `simulated`
- All 10 agent private keys (from `scripts/setup_wallets.py`)

**Pre-configured** (no changes needed):
- `ARC_RPC_URL=https://rpc.testnet.arc.network`
- `ARC_CHAIN_ID=5042002`
- `USDC_CONTRACT_ADDRESS=0x3600000000000000000000000000000000000000`

### Frontend Environment Variables (Vercel)
- `VITE_API_URL` - Your Railway backend URL

### CORS Configuration
Must include your Vercel domain in `engine/orchestrator.py`:
```python
allow_origins=[
    "http://localhost:5173",  # Local dev
    "https://your-domain.vercel.app",  # Production
    "https://*.vercel.app",  # Preview deployments
]
```

## Common Issues

### Issue: CORS Error
**Symptom**: Dashboard shows "Failed to fetch" or CORS policy errors
**Solution**: 
1. Verify Vercel domain is in `orchestrator.py` CORS list
2. Push changes to trigger Railway redeploy
3. Hard refresh browser (Cmd+Shift+R)

### Issue: WebSocket Failed
**Symptom**: "WebSocket connection failed" in console
**Solution**: 
1. Check frontend uses `wss://` not `ws://` for Railway
2. `Dashboard.tsx` line 336 should use `API.replace(/^http/, 'ws')`

### Issue: 404 on Frontend Routes
**Symptom**: `/dashboard` or `/whitepaper` returns 404
**Solution**: 
1. Vercel dashboard → Project Settings → Rewrites
2. Add: `Source: /*` → `Destination: /index.html`

### Issue: Railway Build Fails
**Symptom**: "No module named 'fastapi'" or similar
**Solution**: 
1. Verify `requirements.txt` is in project root
2. Check Railway logs for Python version mismatch
3. Railway uses Python 3.11+ by default

## Post-Deployment Tasks

### 1. Update Documentation URLs
Edit these files with live URLs:
- `README.md` lines 14-15
- `presentation.md` line 255-256

### 2. Test All Features
- [ ] Landing page loads
- [ ] Dashboard streams real-time data
- [ ] Whitepaper displays correct stats (264 txs)
- [ ] WebSocket reconnects after disconnect
- [ ] All API endpoints respond

### 3. Monitor Logs
- Railway: Dashboard → Deployments → View Logs
- Vercel: Dashboard → Deployments → Function Logs

## Success Criteria

✅ **Backend**: `/api/status` returns 200 OK with grid data  
✅ **Frontend**: Dashboard loads and displays live updates  
✅ **WebSocket**: Real-time price updates every 3 seconds  
✅ **No Errors**: Zero CORS, zero 404s, zero 500s  
✅ **Performance**: Page load <2s, WebSocket latency <100ms  

## Next Steps

After successful deployment:
1. **Generate slides** from `presentation.md`
2. **Record video** following `VIDEO_SCRIPT.md`
3. **Take screenshot** of dashboard (1920×1080)
4. **Submit to hackathon** with all materials

---

**Total Time**: 35-45 minutes  
**Deployment Guide**: See `DEPLOYMENT_GUIDE.md` for detailed instructions  
**Repository**: https://github.com/midasbal/GridMint

**Good luck! 🚀**
