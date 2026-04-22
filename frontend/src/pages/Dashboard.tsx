import React, { useEffect, useState, useRef } from 'react'
import ReactDOM from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { useWindowWidth } from '../hooks/useWindowWidth'

// Production API URLs (Railway backend)
const API = import.meta.env.VITE_API_URL || 'https://gridmint-production.up.railway.app'
const GATEWAY_API = 'https://gridmint-production.up.railway.app'  // Same backend handles all APIs
const ARCSCAN = 'https://testnet.arcscan.app'
const GATEWAY = '0x0077777d7EBA4688BDeF3E311b846F25870A19B9'

/* ─── VISUAL LAYERS ─── */
const Scanlines = () => (
  <div style={{position:'fixed',inset:0,zIndex:0,pointerEvents:'none',backgroundImage:'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.07) 2px,rgba(0,0,0,0.07) 4px)'}} />
)
const GridBg = () => (
  <div style={{position:'fixed',inset:0,zIndex:0,pointerEvents:'none',backgroundImage:'linear-gradient(rgba(110,231,243,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(110,231,243,0.025) 1px,transparent 1px)',backgroundSize:'40px 40px'}} />
)

/* ─── TOKENS ─── */
const C = {
  cyan:'#6EE7F3',purple:'#9B8CFF',green:'#4ade80',
  yellow:'#facc15',red:'#f87171',
  dim:'rgba(230,238,246,0.38)',dimmer:'rgba(230,238,246,0.18)',
  text:'#e6eef6',panel:'rgba(255,255,255,0.018)',
  border:'rgba(255,255,255,0.055)',bg:'#030c18',
}

/* ─── TOOLTIP (portal-based — escapes all overflow:hidden ancestors) ─── */
const Tooltip = ({text}:{text:string}) => {
  const [vis,setVis] = useState(false)
  const [pos,setPos] = useState({top:0,left:0})
  const ref = useRef<HTMLDivElement>(null)

  const show = () => {
    if(ref.current){
      const r = ref.current.getBoundingClientRect()
      setPos({
        top: r.top + window.scrollY - 8,   // 8px above the trigger
        left: r.left + r.width/2 + window.scrollX,
      })
    }
    setVis(true)
  }

  const portal = vis ? ReactDOM.createPortal(
    <AnimatePresence>
      <motion.div
        key="tt"
        initial={{opacity:0,y:4,scale:0.95}}
        animate={{opacity:1,y:0,scale:1}}
        exit={{opacity:0,y:4,scale:0.95}}
        transition={{duration:0.15}}
        style={{
          position:'absolute',
          top: pos.top,
          left: pos.left,
          transform:'translate(-50%,-100%)',
          zIndex:2147483647,          // max possible z-index
          background:'rgba(8,20,38,0.97)',
          border:'1px solid rgba(110,231,243,0.2)',
          borderRadius:8,
          padding:'8px 12px',
          width:220,
          fontSize:11,
          color:'rgba(230,238,246,0.78)',
          lineHeight:1.6,
          whiteSpace:'normal',
          pointerEvents:'none',
          boxShadow:'0 8px 32px rgba(0,0,0,0.6)',
        }}>
        <div style={{position:'absolute',bottom:-5,left:'50%',transform:'translateX(-50%)',width:8,height:8,background:'rgba(8,20,38,0.97)',border:'1px solid rgba(110,231,243,0.2)',borderTop:'none',borderLeft:'none',rotate:'45deg'}} />
        {text}
      </motion.div>
    </AnimatePresence>,
    document.body
  ) : null

  return (
    <div ref={ref}
      style={{display:'inline-flex',alignItems:'center',marginLeft:6,flexShrink:0}}
      onMouseEnter={show}
      onMouseLeave={()=>setVis(false)}>
      <div style={{width:14,height:14,borderRadius:'50%',border:`1px solid rgba(110,231,243,0.3)`,display:'flex',alignItems:'center',justifyContent:'center',cursor:'default',fontSize:8,color:'rgba(110,231,243,0.55)',fontWeight:700,userSelect:'none',flexShrink:0}}>?</div>
      {portal}
    </div>
  )
}

/* ─── PRIMITIVES ─── */
const Flip = ({v,color=C.text,size=24}:{v:string|number;color?:string;size?:number}) => (
  <AnimatePresence mode="wait">
    <motion.span key={String(v)} initial={{opacity:0,y:-8}} animate={{opacity:1,y:0}} exit={{opacity:0,y:8}}
      transition={{duration:0.2}}
      style={{fontSize:size,fontWeight:700,color,fontFamily:"'Space Grotesk',ui-sans-serif",letterSpacing:'-0.03em',lineHeight:1}}>
      {v}
    </motion.span>
  </AnimatePresence>
)

const PulseDot = ({color=C.green,size=7}:{color?:string;size?:number}) => (
  <motion.span animate={{boxShadow:[`0 0 0px ${color}`,`0 0 10px ${color}80`,`0 0 0px ${color}`]}}
    transition={{duration:1.8,repeat:Infinity}}
    style={{display:'inline-block',width:size,height:size,borderRadius:'50%',background:color,flexShrink:0}} />
)

const Panel = ({title,accent,badge,children,style,glow,tooltip}:{
  title?:string;accent?:string;badge?:React.ReactNode;children:React.ReactNode;
  style?:React.CSSProperties;glow?:string;tooltip?:string;
}) => {
  // Detect if caller wants flex column layout (has display:flex in style)
  const isFlex = (style as any)?.display === 'flex'
  return (
    <div style={{background:C.panel,border:`1px solid ${accent?`${accent}28`:C.border}`,borderLeft:accent?`3px solid ${accent}`:undefined,borderRadius:16,padding:'16px 18px',position:'relative',boxShadow:glow?`0 0 40px ${glow}10`:undefined,...style}}>
      {glow&&<div style={{position:'absolute',inset:0,overflow:'hidden',borderRadius:16,background:`radial-gradient(ellipse at top left,${glow}05,transparent 65%)`,pointerEvents:'none'}} />}
      {title&&(
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12,position:'relative',flexShrink:0}}>
          <div style={{display:'flex',alignItems:'center'}}>
            <span style={{fontSize:11,fontWeight:700,color:accent??C.dim,textTransform:'uppercase',letterSpacing:'0.09em'}}>{title}</span>
            {tooltip&&<Tooltip text={tooltip}/>}
          </div>
          {badge}
        </div>
      )}
      {/* When flex column, children are direct flex children (no wrapper) */}
      {isFlex ? children : <div style={{position:'relative'}}>{children}</div>}
    </div>
  )
}

const KPI = ({label,value,sub,accent,tooltip}:{label:string;value:React.ReactNode;sub?:string;accent?:string;tooltip?:string}) => (
  <motion.div whileHover={{y:-2}}
    style={{background:C.panel,border:`1px solid ${C.border}`,borderLeft:accent?`3px solid ${accent}`:undefined,borderRadius:14,padding:'14px 16px'}}>
    <div style={{display:'flex',alignItems:'center',marginBottom:6}}>
      <div style={{fontSize:10,color:C.dim,fontWeight:700,textTransform:'uppercase',letterSpacing:'0.08em'}}>{label}</div>
      {tooltip&&<Tooltip text={tooltip}/>}
    </div>
    {value}
    {sub&&<div style={{fontSize:10,color:C.dimmer,marginTop:4}}>{sub}</div>}
  </motion.div>
)

const AgentChip = ({agent,balance,balanceSource}:{agent:any;balance?:number|null;balanceSource?:string}) => {
  const typeColor:Record<string,string>={solar:C.yellow,battery:C.cyan,consumer:C.purple}
  const color=typeColor[agent.agent_type]??C.dim
  const online=agent.status==='online'
  const power=agent.current_output_kw??agent.current_demand_kw??0
  return(
    <motion.div layout whileHover={{scale:1.02}}
      style={{background:online?`${color}08`:C.panel,border:`1px solid ${online?`${color}28`:C.border}`,borderLeft:`3px solid ${online?color:'rgba(255,255,255,0.08)'}`,borderRadius:12,padding:'10px 12px',position:'relative',overflow:'hidden',flexShrink:0}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:5}}>
        <span style={{fontSize:12,fontWeight:700,color:C.text}}>{agent.name??agent.agent_id}</span>
        <PulseDot color={online?C.green:C.red} size={6} />
      </div>
      <div style={{fontSize:9,color,fontWeight:700,textTransform:'uppercase',letterSpacing:'0.07em',marginBottom:6}}>{agent.agent_type}</div>
      <div style={{height:3,background:'rgba(255,255,255,0.06)',borderRadius:2,marginBottom:6,overflow:'hidden'}}>
        <motion.div animate={{width:`${Math.min(100,Math.abs(power)*10)}%`}}
          style={{height:'100%',background:`linear-gradient(90deg,${color},${color}80)`,borderRadius:2}} />
      </div>
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:2}}>
        {agent.agent_type === 'consumer' ? (
          <>
            <div style={{fontSize:10,color:C.dimmer}}>Spent</div>
            <div style={{fontSize:10,color:C.red,fontWeight:600}}>${(agent.total_spent_usd??0).toFixed(4)}</div>
          </>
        ) : (
          <>
            <div style={{fontSize:10,color:C.dimmer}}>Earned</div>
            <div style={{fontSize:10,color:C.green,fontWeight:600}}>${(agent.total_earned_usd??0).toFixed(4)}</div>
          </>
        )}
        <div style={{fontSize:10,color:C.dimmer}}>Net P&L</div>
        <div style={{fontSize:10,color:(agent.total_earned_usd??0)-(agent.total_spent_usd??0)>=0?C.green:C.red,fontWeight:600}}>
          ${((agent.total_earned_usd??0)-(agent.total_spent_usd??0)).toFixed(4)}
        </div>
        <div style={{fontSize:10,color:C.dimmer}}>Trades</div>
        <div style={{fontSize:10,color:C.text}}>{agent.tx_count??0}</div>
        {balance!=null&&<>
          <div style={{fontSize:10,color:C.dimmer}}>USDC</div>
          <div style={{fontSize:10,color:balanceSource==='arc_testnet'?C.green:C.yellow,fontWeight:600}}>
            ${balance.toFixed(4)}<span style={{fontSize:8,opacity:0.6,marginLeft:3}}>{balanceSource==='arc_testnet'?'⛓':'~'}</span>
          </div>
        </>}
      </div>
    </motion.div>
  )
}

const TradeRow = ({t,i}:{t:any;i:number}) => {
  const hash=t.tx_hash as string|undefined
  const isReal=hash&&hash!=='None'&&hash.startsWith('0x')&&hash.length===66
  return(
    <motion.div layout initial={{opacity:0,x:-10}} animate={{opacity:1,x:0}} exit={{opacity:0}}
      transition={{delay:i*0.025}}
      style={{display:'grid',gridTemplateColumns:'1fr 1fr 55px 72px 92px',gap:4,padding:'5px 0',borderBottom:`1px solid ${C.border}`,alignItems:'center'}}>
      <div style={{fontSize:11,color:C.yellow,fontWeight:600}}>{t.seller}</div>
      <div style={{fontSize:11,color:C.purple}}>{t.buyer}</div>
      <div style={{fontSize:11,color:C.text,fontFamily:'monospace'}}>{(t.amount_kwh??0).toFixed(3)}</div>
      <div style={{fontSize:11,color:C.green,fontFamily:'monospace'}}>${(t.total_usd??0).toFixed(5)}</div>
      {isReal
        ?<a href={`${ARCSCAN}/tx/${hash}`} target="_blank" rel="noreferrer"
            style={{fontSize:10,color:C.cyan,textDecoration:'none',fontFamily:'monospace'}} title={hash}>
            {hash!.slice(0,6)}…{hash!.slice(-4)} ↗
          </a>
        :<span style={{fontSize:10,color:C.dimmer,fontFamily:'monospace'}}>{hash?hash.slice(0,10):'—'}</span>
      }
    </motion.div>
  )
}

const ChainRow = ({name,perTx,total,isArc,txCount}:{name:string;perTx:number;total:number;isArc?:boolean;txCount:number}) => {
  const maxTotal=Math.max(txCount*2.47,0.001)
  const pct=Math.min(100,(total/maxTotal)*100)
  return(
    <div style={{display:'grid',gridTemplateColumns:'90px 1fr 72px 80px',gap:8,alignItems:'center',padding:'4px 0'}}>
      <div style={{fontSize:11,fontWeight:700,color:isArc?C.cyan:C.dim}}>{name}</div>
      <div style={{height:5,background:'rgba(255,255,255,0.05)',borderRadius:3,overflow:'hidden'}}>
        <motion.div initial={{width:0}} animate={{width:`${pct}%`}} transition={{duration:0.8}}
          style={{height:'100%',background:isArc?`linear-gradient(90deg,${C.cyan},${C.green})`:'rgba(248,113,113,0.45)',borderRadius:3}} />
      </div>
      <div style={{fontSize:10,color:isArc?C.cyan:C.red,fontFamily:'monospace',textAlign:'right'}}>${perTx.toFixed(isArc?6:3)}</div>
      <div style={{fontSize:10,color:isArc?C.green:'rgba(248,113,113,0.65)',fontFamily:'monospace',textAlign:'right'}}>${total.toFixed(isArc?6:2)}</div>
    </div>
  )
}

const ScenBtn = ({label,scenario,color,onTrigger}:{label:string;scenario:string;color:string;onTrigger:(s:string)=>void}) => (
  <motion.button whileHover={{x:4,background:`${color}12`}} whileTap={{scale:0.97}} onClick={()=>onTrigger(scenario)}
    style={{width:'100%',textAlign:'left',padding:'9px 13px',borderRadius:9,background:`${color}07`,border:`1px solid ${color}22`,color,fontSize:12,fontWeight:600,cursor:'pointer'}}>
    {label}
  </motion.button>
)

/* ─── FAQ ─── */
const FAQ_ITEMS = [
  {q:'What is GridMint?', a:'GridMint is an AI-powered peer-to-peer energy marketplace. Software "agents" representing solar panels, batteries, and consumers automatically buy and sell electricity in real time, settling every transaction directly on the Arc blockchain.'},
  {q:'Why Arc and not Ethereum?', a:'A single trade on Ethereum costs ~$2.47 in gas fees (65,000 gas × 20 gwei × $1,900/ETH). Our trades are worth fractions of a cent. Arc Testnet brings gas costs down by 99.9%+, making micro-energy transactions economically viable for the first time.'},
  {q:'What is USDC and why is it used?', a:'USDC is a stablecoin pegged 1-to-1 to the US dollar. GridMint uses it so energy prices remain stable and predictable — no one wants their electricity bill to change because the crypto market moved.'},
  {q:'What is the x402 paywall?', a:'x402 is an emerging HTTP payment standard. Certain API endpoints (like economic proof data) require a tiny USDC micropayment per request. This demonstrates machine-to-machine commerce without any human involvement.'},
  {q:'What are Shapley Coalitions?', a:'When solar agents and batteries work together, they generate more revenue than alone. Shapley values (a concept from game theory) calculate a mathematically fair share of that revenue for each participant, preventing anyone from being exploited.'},
  {q:'What are Commit-Reveal Futures?', a:'Agents can commit to future energy prices without revealing them immediately (commit phase), then reveal later. This prevents price manipulation. Agents who deviate from their commitment get their deposit "slashed" as a penalty.'},
  {q:'What is Schelling Convergence?', a:'Schelling Point theory predicts that independent rational agents will converge on the same price without talking to each other. The convergence percentage shows how well the 10 agents are naturally agreeing on a fair market price.'},
  {q:'What are the green certificates?', a:'Every unit of energy traded from a solar or renewable source generates a Renewable Energy Certificate (REC). These are recorded on-chain, creating a verifiable audit trail that the energy came from a green source.'},
  {q:'How do I verify the on-chain transactions?', a:'Click any "Verify Txns on ArcScan ↗" button in the dashboard. It opens the ArcScan blockchain explorer directly on the gateway wallet address, showing every real USDC settlement transaction.'},
  {q:'What is the Surge Oracle?', a:'During periods of high demand (e.g., peak afternoon hours), the surge multiplier automatically increases the clearing price — similar to surge pricing in ride-sharing. This incentivizes batteries to discharge and solar to produce more.'},
]

const FAQSection = () => {
  const [open,setOpen] = useState<number|null>(null)
  const w = useWindowWidth()
  const isMobile = w < 768
  return(
    <div style={{marginTop:32,paddingTop:32,borderTop:`1px solid ${C.border}`}}>
      {/* Header */}
      <div style={{display:'flex',alignItems:'center',gap:14,marginBottom:24}}>
        <div style={{flex:1,height:1,background:`linear-gradient(90deg,transparent,${C.cyan}30,transparent)`}} />
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <img src="/gridmint-logo.svg" alt="GridMint" style={{width:28,height:28,opacity:0.85}}/>
          <span style={{fontSize:13,fontWeight:700,color:C.cyan,textTransform:'uppercase',letterSpacing:'0.12em',fontFamily:"'Space Grotesk',ui-sans-serif"}}>Frequently Asked Questions</span>
        </div>
        <div style={{flex:1,height:1,background:`linear-gradient(90deg,transparent,${C.cyan}30,transparent)`}} />
      </div>

      <div style={{display:'grid',gridTemplateColumns:isMobile?'1fr':'1fr 1fr',gap:8,alignItems:'start'}}>
        {FAQ_ITEMS.map((item,i)=>(
          <div key={item.q}
            style={{background:open===i?`rgba(110,231,243,0.04)`:C.panel,border:`1px solid ${open===i?`${C.cyan}28`:C.border}`,borderLeft:`3px solid ${open===i?C.cyan:'rgba(255,255,255,0.06)'}`,borderRadius:12,cursor:'pointer',transition:'border-color 0.2s, background 0.2s'}}
            onClick={()=>setOpen(open===i?null:i)}>
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'13px 16px',gap:12}}>
              <span style={{fontSize:12,fontWeight:600,color:open===i?C.cyan:C.text,flex:1,lineHeight:1.4}}>{item.q}</span>
              <motion.span animate={{rotate:open===i?45:0}} transition={{duration:0.2}}
                style={{fontSize:16,color:open===i?C.cyan:C.dimmer,flexShrink:0,lineHeight:1}}>+</motion.span>
            </div>
            <div style={{
              maxHeight: open===i ? '400px' : '0px',
              overflow: 'hidden',
              transition: 'max-height 0.3s ease',
            }}>
              <div style={{padding:'0 16px 14px',fontSize:12,color:C.dim,lineHeight:1.7,borderTop:`1px solid ${C.border}`}}>
                <div style={{paddingTop:10}}>{item.a}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{marginTop:28,display:'flex',justifyContent:'space-between',alignItems:'center',padding:'16px 20px',background:'rgba(255,255,255,0.01)',border:`1px solid ${C.border}`,borderRadius:12}}>
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <img src="/gridmint-logo.svg" alt="GridMint" style={{width:22,height:22,opacity:0.7}}/>
          <div>
            <div style={{fontSize:12,fontWeight:700,color:C.text,fontFamily:"'Space Grotesk',ui-sans-serif"}}>GridMint</div>
            <div style={{fontSize:10,color:C.dimmer}}>Agentic Energy Economy · Arc Testnet</div>
          </div>
        </div>
        <div style={{display:'flex',gap:16,alignItems:'center'}}>
          {[
            {label:'ArcScan',href:`${ARCSCAN}/address/${GATEWAY}`},
            {label:'x402 Spec',href:'https://github.com/coinbase/x402'},
            {label:'Arc Docs',href:'https://docs.arc.network'},
          ].map(l=>(
            <a key={l.label} href={l.href} target="_blank" rel="noreferrer"
              style={{fontSize:11,color:C.dim,textDecoration:'none',fontWeight:500,transition:'color 0.15s'}}
              onMouseEnter={e=>(e.currentTarget.style.color=C.cyan)} onMouseLeave={e=>(e.currentTarget.style.color=C.dim)}>
              {l.label} ↗
            </a>
          ))}
        </div>
        <div style={{fontSize:10,color:C.dimmer}}>Agentic Economy on Arc</div>
      </div>
    </div>
  )
}

/* ═══════════════════════════════════════════════
   DASHBOARD
═══════════════════════════════════════════════ */
export default function Dashboard() {
  const nav = useNavigate()
  const prevNarrative = useRef('')
  const w = useWindowWidth()
  const isMobile = w < 768
  const isTablet = w < 1100

  const [snap,setSnap] = useState<any>(null)
  const [connected,setConnected] = useState(false)
  const [agents,setAgents] = useState<any[]>([])
  const [trades,setTrades] = useState<any[]>([])
  const [running,setRunning] = useState(false)
  const [settlementMode,setSettlementMode] = useState('simulated')
  const [balances,setBalances] = useState<Record<string,{balance_usd:number|null;source:string}>>({})
  const [economicProof,setEconomicProof] = useState<any>(null)
  const [certs,setCerts] = useState<any>(null)
  const [x402,setX402] = useState<any>(null)
  const [coalitions,setCoalitions] = useState<any>(null)
  const [futures,setFutures] = useState<any>(null)
  const [stressResult,setStressResult] = useState('')
  const [geminiQ,setGeminiQ] = useState('')
  const [geminiA,setGeminiA] = useState('')
  const [geminiLoading,setGeminiLoading] = useState(false)
  const [geminiRateLimited,setGeminiRateLimited] = useState(false)

  useEffect(()=>{
    let ws:WebSocket, retryTimer:ReturnType<typeof setTimeout>
    const connect=()=>{
      // Replace http/https with ws/wss for WebSocket protocol
      const wsUrl = API.replace(/^http/, 'ws')
      ws=new WebSocket(`${wsUrl}/ws`)
      ws.addEventListener('open',()=>setConnected(true))
      ws.addEventListener('close',()=>{setConnected(false);retryTimer=setTimeout(connect,3000)})
      ws.addEventListener('error',()=>ws.close())
      ws.addEventListener('message',(ev)=>{
        try{
          const msg=JSON.parse(ev.data)
          if(msg.type==='snapshot'){
            setSnap(msg)
            const narrative=msg.gemini?.narrative??''
            const lastErr=msg.gemini?.stats?.last_error??''
            if(prevNarrative.current&&!narrative&&(lastErr.includes('429')||lastErr.includes('quota'))){
              setGeminiRateLimited(true);setTimeout(()=>setGeminiRateLimited(false),15000)
            }
            if(narrative){prevNarrative.current=narrative;setGeminiRateLimited(false)}
            if(msg.coalitions)setCoalitions((p:any)=>({...(p??{}),stats:msg.coalitions}))
            if(msg.futures)setFutures((p:any)=>({...(p??{}),stats:msg.futures}))
          }
        }catch{}
      })
    }
    connect()
    return()=>{ws?.close();clearTimeout(retryTimer)}
  },[])

  useEffect(()=>{
    const DUMMY='0x0000000000000000000000000000000000000000000000000000000000000000'
    const poll=async()=>{
      try{
        const [ag,tr,st,ep,ce,x4,co,fu]=await Promise.all([
          axios.get(`${API}/api/agents`),
          axios.get(`${API}/api/payments?limit=20`),
          axios.get(`${API}/api/status`),
          axios.get(`${GATEWAY_API}/api/economic-proof`,{headers:{'PAYMENT-SIGNATURE':DUMMY}}).catch(()=>({data:null})),
          axios.get(`${GATEWAY_API}/api/certificates`,{headers:{'PAYMENT-SIGNATURE':DUMMY}}).catch(()=>({data:null})),
          axios.get(`${API}/api/x402`).catch(()=>({data:null})),
          axios.get(`${API}/api/coalitions`).catch(()=>({data:null})),
          axios.get(`${API}/api/futures`).catch(()=>({data:null})),
        ])
        setAgents(ag.data??[])
        setTrades(tr.data?.recent??[])
        setRunning(st.data?.running??false)
        setSettlementMode(st.data?.settlement_mode??'simulated')
        
        // BUGFIX: If economic-proof is unavailable (paywalled), synthesize from /api/status
        // This ensures Green Energy % always displays even if x402 blocks the request
        if(ep.data&&ep.data.total_transactions!==undefined){
          setEconomicProof(ep.data)
        }else if(st.data&&st.data.total_tx_count!==undefined){
          // Fallback: construct minimal economicProof from /api/status
          setEconomicProof({
            total_transactions:st.data.total_tx_count,
            total_usd_settled:st.data.total_usd_settled,
            green_energy_pct:st.data.green_energy_pct??0,
            clearing_price_usd:st.data.clearing_price_usd??0,
          })
        }
        
        if(ce.data&&ce.data.stats)setCerts(ce.data)
        if(x4.data)setX402(x4.data)
        if(co.data)setCoalitions(co.data)
        if(fu.data)setFutures(fu.data)
      }catch{}
    }
    poll();const id=setInterval(poll,5000);return()=>clearInterval(id)
  },[])

  useEffect(()=>{
    const fetch=async()=>{
      try{
        const r=await axios.get(`${API}/api/balances`)
        const map:Record<string,{balance_usd:number|null;source:string}>={}
        for(const [id,v] of Object.entries(r.data as any))
          map[id]={balance_usd:(v as any).balance_usd??null,source:(v as any).source??'simulated'}
        setBalances(map)
      }catch{}
    }
    fetch();const id=setInterval(fetch,8000);return()=>clearInterval(id)
  },[])

  const toggleSim=async()=>{
    try{
      if(running){await axios.post(`${API}/api/grid/stop`);setRunning(false)}
      else{await axios.post(`${API}/api/grid/start`);setRunning(true)}
    }catch{}
  }
  const resetToDawn=async()=>{
    try{await axios.post(`${API}/api/grid/reset`);setRunning(true)}catch{}
  }
  const downloadProof=async()=>{
    try{
      const r=await axios.get(`${API}/api/live-proof`)
      const blob=new Blob([JSON.stringify(r.data,null,2)],{type:'application/json'})
      const url=URL.createObjectURL(blob)
      const a=document.createElement('a');a.href=url;a.download='live_proof.json';a.click()
      URL.revokeObjectURL(url)
    }catch{}
  }
  const triggerStress=async(scenario:string)=>{
    try{const r=await axios.post(`${API}/api/stress/${scenario}`);setStressResult(r.data?.status??'Triggered');setTimeout(()=>setStressResult(''),5000)}
    catch{setStressResult('Error')}
  }
  const askGemini=async()=>{
    if(!geminiQ.trim())return
    setGeminiLoading(true);setGeminiA('')
    try{
      const r=await axios.post(`${API}/api/gemini/ask`,{question:geminiQ})
      const ans=r.data.answer??''
      if(ans.includes('429')||ans.toLowerCase().includes('quota')||ans.toLowerCase().includes('rate limit')){
        setGeminiRateLimited(true);setTimeout(()=>setGeminiRateLimited(false),15000)
      }else{setGeminiA(ans||'No response.')}
    }catch{}
    setGeminiLoading(false)
  }

  const payments=snap?.payments??{}
  const data=snap?.data??{}
  const isLive=settlementMode==='live'
  const txCount:number=payments.success_count??data.total_tx_count??0
  const chainComp=economicProof?.chain_comparison??{}
  const arcScanGateway=`${ARCSCAN}/address/${GATEWAY}`
  const simH=data.sim_hour??0
  const simHH=String(Math.floor(simH%24)).padStart(2,'0')
  const simMM=String(Math.floor((simH%1)*60)).padStart(2,'0')

  return(
    <div style={{background:C.bg,minHeight:'100vh',color:C.text,fontFamily:"'Inter',ui-sans-serif,system-ui",position:'relative'}}>
      <Scanlines/><GridBg/>

      {/* TOP BAR */}
      <div style={{position:'sticky',top:0,zIndex:100,background:'rgba(3,12,24,0.92)',backdropFilter:'blur(24px)',borderBottom:`1px solid ${C.border}`,padding:`0 ${isMobile?12:24}px`,height:isMobile?50:58,display:'flex',alignItems:'center',justifyContent:'space-between',gap:8}}>
        <div style={{display:'flex',alignItems:'center',gap:isMobile?6:12,flexShrink:0}}>
          <button onClick={()=>nav('/')} style={{background:'none',border:'none',color:C.dim,cursor:'pointer',fontSize:16,padding:'4px 6px'}}>←</button>
          <img src="/gridmint-logo.svg" alt="GridMint" style={{width:24,height:24}}/>
          <span style={{fontFamily:"'Space Grotesk',ui-sans-serif",fontWeight:700,fontSize:isMobile?13:15,letterSpacing:'-0.02em'}}>GridMint</span>
          {!isMobile&&<span style={{fontSize:10,color:C.dimmer}}>/ Mission Control</span>}
          <motion.div animate={isLive?{boxShadow:[`0 0 0px ${C.red}`,`0 0 10px ${C.red}60`,`0 0 0px ${C.red}`]}:{}}
            transition={{duration:2,repeat:Infinity}}
            style={{display:'flex',alignItems:'center',gap:5,padding:'3px 8px',borderRadius:20,background:isLive?'rgba(248,113,113,0.1)':'rgba(250,204,21,0.07)',border:`1px solid ${isLive?'rgba(248,113,113,0.3)':'rgba(250,204,21,0.2)'}`,fontSize:9,fontWeight:700,color:isLive?C.red:C.yellow,textTransform:'uppercase',letterSpacing:'0.08em'}}>
            <PulseDot color={isLive?C.red:C.yellow} size={5}/>
            {isMobile?(isLive?'Live':'Sim'):(isLive?'Arc Testnet Live':'Simulated')}
          </motion.div>
        </div>

        {!isMobile&&<div style={{position:'absolute',left:'50%',transform:'translateX(-50%)',display:'flex',flexDirection:'column',alignItems:'center'}}>
          <div style={{fontSize:20,fontWeight:700,fontFamily:"'Space Grotesk',ui-sans-serif",color:C.cyan,letterSpacing:'0.04em'}}>{simHH}:{simMM}</div>
          <div style={{fontSize:9,color:C.dimmer,textTransform:'uppercase',letterSpacing:'0.1em',marginTop:-2}}>Sim Time · Tick {data.tick??'—'}</div>
        </div>}

        <div style={{display:'flex',alignItems:'center',gap:isMobile?6:10,flexShrink:0}}>
          {!isMobile&&<motion.button 
            whileHover={{scale:1.06,y:-2,boxShadow:'0 6px 20px rgba(155,140,255,0.4)'}} 
            whileTap={{scale:0.94}} 
            onClick={()=>nav('/whitepaper')}
            style={{
              padding:'8px 16px',
              background:'linear-gradient(135deg, rgba(155,140,255,0.18) 0%, rgba(110,231,243,0.14) 100%)',
              border:'1px solid rgba(155,140,255,0.4)',
              borderRadius:10,
              color:'#e6eef6',
              fontSize:11,
              fontWeight:700,
              cursor:'pointer',
              backdropFilter:'blur(12px)',
              boxShadow:'0 4px 14px rgba(155,140,255,0.2), inset 0 1px 0 rgba(255,255,255,0.12)',
              display:'flex',
              alignItems:'center',
              gap:7,
              letterSpacing:'0.02em'
            }}>
            <span style={{fontSize:13}}>📄</span>
            <span style={{
              background:'linear-gradient(90deg, #9B8CFF 0%, #6EE7F3 100%)',
              WebkitBackgroundClip:'text',
              WebkitTextFillColor:'transparent'
            }}>Whitepaper</span>
          </motion.button>}
          {!isMobile&&<div style={{display:'flex',alignItems:'center',gap:6,fontSize:11,color:connected?C.green:C.red,fontWeight:600}}>
            <PulseDot color={connected?C.green:C.red} size={6}/>
            {connected?'WS Live':'Reconnecting…'}
          </div>}
          {!isMobile&&<motion.button whileHover={{scale:1.04}} whileTap={{scale:0.97}} onClick={resetToDawn}
            style={{padding:'6px 12px',borderRadius:9,background:'rgba(250,204,21,0.08)',color:C.yellow,fontWeight:700,fontSize:11,border:`1px solid rgba(250,204,21,0.2)`,cursor:'pointer'}}>
            🌅 Dawn
          </motion.button>}
          <motion.button whileHover={{scale:1.04}} whileTap={{scale:0.97}} onClick={toggleSim}
            style={{padding:isMobile?'6px 10px':'7px 16px',borderRadius:9,background:running?'rgba(248,113,113,0.1)':`linear-gradient(90deg,${C.cyan},${C.purple})`,color:running?C.red:'#020e18',fontWeight:700,fontSize:isMobile?11:12,border:running?`1px solid rgba(248,113,113,0.25)`:'none',cursor:'pointer',whiteSpace:'nowrap'}}>
            {running?(isMobile?'⏹':'⏹ Stop'):(isMobile?'▶':'▶ Start')}
          </motion.button>
        </div>
      </div>

      {/* BODY */}
      <div style={{maxWidth:1440,margin:'0 auto',padding:`16px ${isMobile?12:20}px 50px`,position:'relative',zIndex:1}}>

        {/* KPI strip */}
        <div style={{display:'grid',gridTemplateColumns:isMobile?'repeat(2,1fr)':isTablet?'repeat(3,1fr)':'repeat(6,1fr)',gap:isMobile?8:10,marginBottom:14}}>
          <KPI label="On-Chain Txns" accent={C.cyan} tooltip="Total number of energy trades settled as real USDC transactions on the Arc blockchain. Target: 50+ to prove the system works at scale."
            value={<Flip v={txCount} color={C.cyan} size={28}/>}
            sub={txCount>=50?'✅ 50+ target met':`${Math.max(0,50-txCount)} to 50+ target`}/>
          <KPI label="Clearing Price" tooltip="The market-clearing price per kilowatt-hour in USDC, determined by matching buy and sell orders from all agents each tick. Shows $0.0000 during nighttime hours (8 PM - 6 AM) when no trades occur."
            value={<Flip v={`$${(data.clearing_price_usd??0).toFixed(4)}`} size={22}/>}
            sub={data.sim_hour<6||data.sim_hour>20?'🌙 Night (no solar)':'☀️ Daytime'}/>
          <KPI label="Total Settled" accent={C.green} tooltip="The total dollar value of USDC transferred between wallets on the Arc blockchain. This is real money moving on-chain."
            value={<Flip v={`$${(payments.total_settled_usd??0).toFixed(5)}`} color={C.green} size={20}/>}
            sub="USDC on Arc"/>
          <KPI label="Arc Gas Cost" tooltip="The total gas fees paid to the Arc network for all transactions combined. This is the actual cost of using the blockchain — compare it to Ethereum below."
            value={<Flip v={`$${(payments.total_gas_usd??0).toFixed(6)}`} size={20}/>}
            sub="actual on-chain"/>
          <KPI label="Savings vs ETH" accent={C.purple} tooltip="How many times cheaper Arc is than Ethereum for the same trades. Calculated using 65,000 gas × 20 gwei × $1,900/ETH — the 2024 median cost of an ERC-20 USDC transfer."
            value={<Flip v={payments.arc_savings_vs_eth?`${payments.arc_savings_vs_eth}×`:'—'} color={C.purple} size={26}/>}
            sub="65k gas·20gwei·$1900"/>
          <KPI label="Green Energy" tooltip="Percentage of all traded energy that came from renewable sources (solar panels). Each renewable trade generates a verifiable on-chain Renewable Energy Certificate (REC)."
            value={<Flip v={`${economicProof?.green_energy_pct??0}%`} color={C.green} size={26}/>}
            sub="renewable trades"/>
        </div>

        {/* ROW A */}
        <div style={{display:'grid',gridTemplateColumns:isMobile?'1fr':isTablet?'1fr':'270px 1fr 220px',gap:12,marginBottom:12}}>

          {/* Agent Fleet — fully scrollable */}
          <Panel title="Agent Fleet" accent={C.cyan} glow={C.cyan}
            tooltip="All 10 autonomous software agents: 3 solar generators (sell energy), 5 consumers (buy energy), and 2 batteries (store and trade). Each has its own blockchain wallet."
            badge={<span style={{fontSize:10,color:C.dimmer}}>{agents.length} agents</span>}
            style={{display:'flex',flexDirection:'column',height:isMobile?300:560,overflow:'hidden'}}>
            <div style={{overflowY:'auto',flex:1,display:'flex',flexDirection:'column',gap:8,paddingRight:2,minHeight:0}}>
              {agents.length===0
                ?<div style={{fontSize:12,color:C.dimmer,textAlign:'center',padding:'24px 0'}}>Start simulation…</div>
                :agents.map((a:any)=>(
                  <AgentChip key={a.agent_id} agent={a}
                    balance={balances[a.agent_id]?.balance_usd??null}
                    balanceSource={balances[a.agent_id]?.source}/>
                ))}
            </div>
          </Panel>

          {/* Center */}
          <div style={{display:'flex',flexDirection:'column',gap:12}}>
            <Panel title="On-Chain Trade Stream" accent={C.green} glow={C.green}
              tooltip="Every row is a real energy trade: who sold, who bought, how many kWh, the USDC price, and a clickable link to verify the transaction on the Arc blockchain explorer."
              badge={
                <a href={arcScanGateway} target="_blank" rel="noreferrer"
                  style={{fontSize:10,color:C.cyan,fontWeight:700,textDecoration:'none',border:`1px solid ${C.cyan}30`,borderRadius:6,padding:'2px 8px',background:`${C.cyan}08`}}>
                  🔍 Verify {txCount} Txns on ArcScan ↗
                </a>
              }>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 55px 72px 92px',gap:4,marginBottom:5}}>
                {['Seller','Buyer','kWh','USDC','Hash'].map(h=>(
                  <div key={h} style={{fontSize:9,color:C.dimmer,fontWeight:700,textTransform:'uppercase',letterSpacing:'0.07em'}}>{h}</div>
                ))}
              </div>
              <div style={{maxHeight:230,overflowY:'auto'}}>
                <AnimatePresence>
                  {trades.length===0
                    ?<div style={{fontSize:12,color:C.dimmer,textAlign:'center',padding:'20px 0'}}>No trades yet</div>
                    :trades.slice(0,15).map((t,i)=><TradeRow key={i} t={t} i={i}/>)}
                </AnimatePresence>
              </div>
              {txCount>=50&&(
                <motion.div initial={{opacity:0}} animate={{opacity:1}}
                  style={{marginTop:10,display:'flex',alignItems:'center',gap:8,padding:'8px 12px',background:`${C.green}08`,border:`1px solid ${C.green}25`,borderRadius:8}}>
                  <PulseDot color={C.green}/>
                  <span style={{fontSize:11,color:C.green,fontWeight:700}}>✅ {txCount} on-chain transactions confirmed</span>
                  <a href={arcScanGateway} target="_blank" rel="noreferrer"
                    style={{fontSize:11,color:C.cyan,marginLeft:'auto',textDecoration:'none',fontWeight:600}}>View all ↗</a>
                </motion.div>
              )}
            </Panel>

            {/* Gemini */}
            <Panel title="Gemini AI · Market Intelligence" accent={C.purple} glow={C.purple}
              tooltip="Google Gemini AI analyzes the live grid state every tick and writes a market commentary. You can also ask it custom questions about what the agents are doing and why."
              badge={
                geminiRateLimited
                  ?<motion.span animate={{opacity:[1,0.5,1]}} transition={{duration:1.2,repeat:Infinity}}
                      style={{fontSize:10,color:C.yellow,background:`${C.yellow}10`,border:`1px solid ${C.yellow}25`,borderRadius:6,padding:'2px 8px',fontWeight:600}}>
                      ⚡ Rate limited · retrying…
                    </motion.span>
                  :snap?.gemini?.stats?.available
                    ?<span style={{fontSize:10,color:C.green,fontWeight:600}}>● Active</span>
                    :<span style={{fontSize:10,color:C.dimmer}}>○ Offline</span>
              }>
              {!geminiRateLimited&&snap?.gemini?.narrative&&(
                <motion.div key={snap.gemini.narrative} initial={{opacity:0}} animate={{opacity:1}}
                  style={{background:`${C.purple}08`,border:`1px solid ${C.purple}18`,borderRadius:8,padding:'8px 12px',fontSize:12,color:`${C.text}88`,lineHeight:1.65,marginBottom:10,maxHeight:60,overflow:'hidden'}}>
                  {snap.gemini.narrative}
                </motion.div>
              )}
              {geminiRateLimited&&(
                <div style={{background:`${C.yellow}07`,border:`1px solid ${C.yellow}18`,borderRadius:8,padding:'8px 12px',fontSize:12,color:C.yellow,marginBottom:10,lineHeight:1.55}}>
                  Gemini is temporarily rate-limited. The AI console will resume automatically. No action needed.
                </div>
              )}
              <div style={{display:'flex',gap:8}}>
                <input value={geminiQ} onChange={e=>setGeminiQ(e.target.value)}
                  placeholder="Ask the grid… e.g. Why did battery_01 discharge?"
                  style={{flex:1,background:'rgba(255,255,255,0.025)',border:`1px solid ${C.border}`,borderRadius:8,padding:'8px 12px',color:C.text,fontSize:12,outline:'none',fontFamily:'inherit'}}
                  onKeyDown={e=>{if(e.key==='Enter')askGemini()}}/>
                <motion.button whileHover={{scale:1.04}} whileTap={{scale:0.97}} onClick={askGemini} disabled={geminiLoading||geminiRateLimited}
                  style={{padding:'8px 14px',borderRadius:8,background:`linear-gradient(90deg,${C.cyan},${C.purple})`,color:'#020e18',fontWeight:700,fontSize:12,border:'none',cursor:'pointer',opacity:(geminiLoading||geminiRateLimited)?0.5:1}}>
                  {geminiLoading?'…':'Ask'}
                </motion.button>
              </div>
              <AnimatePresence>
                {geminiA&&(
                  <motion.div key={geminiA} initial={{opacity:0,y:4}} animate={{opacity:1,y:0}} exit={{opacity:0}}
                    style={{marginTop:8,background:`${C.purple}07`,border:`1px solid ${C.purple}15`,borderRadius:8,padding:'8px 12px',fontSize:12,color:`${C.text}80`,lineHeight:1.65,maxHeight:110,overflowY:'auto'}}>
                    {geminiA}
                  </motion.div>
                )}
              </AnimatePresence>
            </Panel>
          </div>

          {/* Right */}
          <div style={{display:'flex',flexDirection:'column',gap:12}}>
            <Panel title="Surge Oracle" accent={C.yellow}
              tooltip="During peak demand periods, the surge multiplier increases energy prices automatically — like ride-share surge pricing. This incentivizes batteries to sell stored power and balances the grid.">
              {snap?.surge?(
                <div style={{fontSize:12,lineHeight:2.1,color:C.dim}}>
                  <div>Multiplier <span style={{color:C.yellow,fontWeight:700,fontSize:20,fontFamily:"'Space Grotesk',ui-sans-serif"}}>{snap.surge.current_multiplier??'—'}×</span></div>
                  <div>Zone <span style={{color:C.text}}>{snap.surge.zone??'—'}</span></div>
                  <div>Stress <span style={{color:C.purple}}>{snap.surge.stress_index??'—'}</span></div>
                </div>
              ):<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'10px 0'}}>Waiting…</div>}
            </Panel>

            <Panel title="Schelling Convergence" accent={C.purple}
              tooltip="Schelling Point theory: independent rational agents will naturally agree on the same price without communicating. This percentage shows how closely all 10 agents are converging on a single fair market price.">
              {snap?.schelling?(
                <>
                  <div style={{height:5,background:'rgba(255,255,255,0.05)',borderRadius:3,overflow:'hidden',marginBottom:6}}>
                    <motion.div animate={{width:`${snap.schelling.convergence_pct??0}%`}}
                      style={{height:'100%',background:`linear-gradient(90deg,${C.purple},${C.cyan})`,borderRadius:3}}/>
                  </div>
                  <div style={{fontSize:22,fontWeight:700,color:C.purple,fontFamily:"'Space Grotesk',ui-sans-serif",marginBottom:6}}>{snap.schelling.convergence_pct??0}%</div>
                  <div style={{fontSize:12,color:C.dim,lineHeight:2}}>
                    <div>Spread <span style={{color:C.text}}>${(snap.schelling.price_spread??0).toFixed(4)}</span></div>
                  </div>
                </>
              ):<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'10px 0'}}>Waiting…</div>}
            </Panel>

            <Panel title="Stress Tests" accent={C.red}
              tooltip="Inject real-world grid failure scenarios to test the system's resilience. Watch how agent prices and behaviors adapt in real time when something goes wrong.">
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                <ScenBtn label="☀ Solar Dropout" scenario="solar_dropout" color={C.yellow} onTrigger={triggerStress}/>
                <ScenBtn label="📈 Demand Surge" scenario="demand_surge" color={C.red} onTrigger={triggerStress}/>
                <ScenBtn label="🔋 Battery Drain" scenario="battery_drain" color={C.cyan} onTrigger={triggerStress}/>
                <ScenBtn label="🕸 Net Partition" scenario="network_partition" color={C.purple} onTrigger={triggerStress}/>
              </div>
              <AnimatePresence>
                {stressResult&&(
                  <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}
                    style={{marginTop:8,padding:'6px 10px',background:`${C.green}08`,border:`1px solid ${C.green}20`,borderRadius:6,fontSize:11,color:C.green}}>
                    ✓ {stressResult}
                  </motion.div>
                )}
              </AnimatePresence>
            </Panel>
          </div>
        </div>

        {/* ECONOMIC PROOF */}
        <motion.div initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{delay:0.1}}
          style={{background:`linear-gradient(135deg,${C.cyan}06,${C.purple}06)`,border:`1px solid ${C.cyan}20`,borderRadius:16,padding:'18px 20px',marginBottom:12}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
            <div>
              <div style={{display:'flex',alignItems:'center'}}>
                <div style={{fontSize:11,fontWeight:700,color:C.cyan,textTransform:'uppercase',letterSpacing:'0.09em'}}>📊 Economic Proof</div>
                <Tooltip text="This table proves mathematically that sub-cent energy trades are only economically viable on Arc. The ETH cost is sourced from real 2024 on-chain data: 65k gas for an ERC-20 transfer × 20 gwei gas price × $1,900/ETH."/>
              </div>
              <div style={{fontSize:11,color:C.dim,marginTop:2}}>Mathematical proof that sub-cent trades are only viable on Arc. ETH model: 65k gas × 20 gwei × $1,900/ETH (2024 median ERC-20).</div>
            </div>
            <div style={{display:'flex',gap:8,alignItems:'center'}}>
              <a href={arcScanGateway} target="_blank" rel="noreferrer"
                style={{display:'flex',alignItems:'center',gap:6,padding:'8px 14px',background:`${C.cyan}10`,border:`1px solid ${C.cyan}30`,borderRadius:9,fontSize:12,color:C.cyan,fontWeight:700,textDecoration:'none',whiteSpace:'nowrap'}}>
                🔍 {txCount} Txns on ArcScan ↗
              </a>
              <motion.button whileHover={{scale:1.04}} whileTap={{scale:0.97}} onClick={downloadProof}
                style={{padding:'8px 14px',borderRadius:9,background:`${C.purple}10`,color:C.purple,fontWeight:700,fontSize:12,border:`1px solid ${C.purple}30`,cursor:'pointer',whiteSpace:'nowrap'}}>
                ⬇ live_proof.json
              </motion.button>
            </div>
          </div>
          <div style={{display:'grid',gridTemplateColumns:isMobile?'1fr':'1fr 1fr',gap:12}}>
            <div style={{background:'rgba(0,0,0,0.25)',borderRadius:12,padding:'14px 16px'}}>
              <div style={{display:'flex',justifyContent:'space-between',marginBottom:8}}>
                <div style={{fontSize:10,color:C.dim,fontWeight:700,textTransform:'uppercase',letterSpacing:'0.07em'}}>Gas Cost — {txCount} txns</div>
                <div style={{fontSize:9,display:'grid',gridTemplateColumns:'90px 1fr 72px 80px',gap:8,color:C.dimmer}}>
                  <span/><span/><span style={{textAlign:'right'}}>Per Tx</span><span style={{textAlign:'right'}}>Total</span>
                </div>
              </div>
              {Object.keys(chainComp).length>0
                ?Object.entries(chainComp).map(([name,d]:any)=>(
                  <ChainRow key={name} name={name.charAt(0).toUpperCase()+name.slice(1)}
                    perTx={d.per_tx??0} total={d.total??0} isArc={name==='arc'} txCount={txCount}/>
                ))
                :<>
                    {([['Ethereum',2.47],['Arbitrum',0.048],['Base',0.031],['Polygon',0.009],['Solana',0.0025]] as [string,number][]).map(([n,p])=>(
                      <ChainRow key={n} name={n} perTx={p} total={p*txCount} txCount={txCount}/>
                    ))}
                    <ChainRow name="Arc" perTx={payments.avg_gas_per_tx??0} total={payments.total_gas_usd??0} isArc txCount={txCount}/>
                  </>
              }
              {economicProof?.eth_gas_model&&(
                <div style={{marginTop:6,fontSize:9,color:C.dimmer,fontStyle:'italic'}}>Model: {economicProof.eth_gas_model}</div>
              )}
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
                {[
                  {l:'Avg Arc Cost/Tx',v:economicProof?.avg_cost_per_tx_usd!=null?`$${Number(economicProof.avg_cost_per_tx_usd).toFixed(6)}`:'—',c:C.green,n:'Target ≤$0.01'},
                  {l:'ETH Shadow Cost',v:`$${(economicProof?.traditional_eth_gas_cost_usd??0).toFixed(2)}`,c:C.red,n:'65k gas × 20gwei × $1,900'},
                  {l:'Savings vs ETH',v:economicProof?.savings_vs_eth_pct!=null?`${economicProof.savings_vs_eth_pct}%`:'—',c:C.cyan,n:''},
                  {l:'Savings Factor',v:economicProof?.arc_savings_factor?`${economicProof.arc_savings_factor}×`:'—',c:C.purple,n:''},
                ].map((s,i)=>(
                  <div key={i} style={{background:'rgba(0,0,0,0.2)',borderRadius:10,padding:'10px 12px'}}>
                    <div style={{fontSize:9,color:C.dimmer,textTransform:'uppercase',letterSpacing:'0.06em',marginBottom:4}}>{s.l}</div>
                    <div style={{fontSize:20,fontWeight:700,color:s.c,fontFamily:"'Space Grotesk',ui-sans-serif"}}>{s.v}</div>
                    {s.n&&<div style={{fontSize:9,color:C.dimmer,marginTop:2}}>{s.n}</div>}
                  </div>
                ))}
              </div>
              {economicProof?.merkle_root&&(
                <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 12px',background:`${C.green}07`,border:`1px solid ${C.green}20`,borderRadius:10}}>
                  <span>🌿</span>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontSize:9,color:C.green,fontWeight:700,textTransform:'uppercase',letterSpacing:'0.07em'}}>Green Merkle Root</div>
                    <div style={{fontFamily:'monospace',fontSize:9,color:C.dimmer,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',marginTop:2}}>{String(economicProof.merkle_root)}</div>
                  </div>
                  <span style={{fontSize:11,color:C.green,fontWeight:700}}>{economicProof.green_energy_pct??0}%</span>
                </div>
              )}
            </div>
          </div>
        </motion.div>

        {/* COALITIONS + FUTURES */}
        <div style={{display:'grid',gridTemplateColumns:isMobile?'1fr':'1fr 1fr',gap:12,marginBottom:12}}>
          <Panel title="🤝 Shapley Coalitions" accent={C.cyan} glow={C.cyan}
            tooltip="Groups of solar and battery agents form coalitions to earn more revenue together than separately. Shapley values (from cooperative game theory) distribute profits fairly based on each agent's marginal contribution."
            badge={coalitions?.stats&&<span style={{fontSize:10,color:C.cyan,background:`${C.cyan}10`,padding:'2px 7px',borderRadius:6,fontWeight:600}}>{coalitions.stats.total_formed??0} formed</span>}>
            {coalitions?.stats?(
              <>
                <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8,marginBottom:10}}>
                  {[{l:'Active',v:String(coalitions.stats.active??0),c:C.cyan},{l:'Revenue',v:`$${(coalitions.stats.total_revenue_usd??0).toFixed(4)}`,c:C.green},{l:'Dispatchable',v:String(coalitions.stats.total_dispatchable??0),c:C.purple}].map((s,i)=>(
                    <div key={i} style={{background:'rgba(0,0,0,0.2)',borderRadius:9,padding:'9px 11px',textAlign:'center'}}>
                      <div style={{fontSize:17,fontWeight:700,color:s.c,fontFamily:"'Space Grotesk',ui-sans-serif"}}>{s.v}</div>
                      <div style={{fontSize:9,color:C.dimmer,marginTop:2,textTransform:'uppercase',letterSpacing:'0.05em'}}>{s.l}</div>
                    </div>
                  ))}
                </div>
                <div style={{maxHeight:180,overflowY:'auto',display:'flex',flexDirection:'column',gap:5}}>
                  {(coalitions.recent??[]).length===0
                    ?<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'14px 0'}}>Run simulation to see coalitions</div>
                    :(coalitions.recent??[]).map((c:any,i:number)=>(
                      <motion.div key={i} initial={{opacity:0}} animate={{opacity:1}}
                        style={{background:'rgba(255,255,255,0.02)',border:`1px solid ${c.is_dispatchable?`${C.green}20`:C.border}`,borderRadius:9,padding:'7px 10px'}}>
                        <div style={{display:'flex',justifyContent:'space-between',marginBottom:3}}>
                          <span style={{fontSize:10,color:c.is_dispatchable?C.green:C.cyan,fontWeight:600}}>{c.is_dispatchable?'⚡ Dispatch':'☀ Basic'}</span>
                          <span style={{fontSize:10,color:C.green}}>${(c.revenue_usd??0).toFixed(4)}</span>
                        </div>
                        <div style={{fontSize:10,color:C.dim}}>{c.members?.map((m:any)=>m.agent_id).join(' + ')}</div>
                        {c.shapley_values&&Object.keys(c.shapley_values).length>0&&(
                          <div style={{fontSize:9,color:`${C.purple}80`,marginTop:2}}>φ: {Object.entries(c.shapley_values).map(([k,v])=>`${k}=$${Number(v).toFixed(4)}`).join(', ')}</div>
                        )}
                      </motion.div>
                    ))}
                </div>
              </>
            ):<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'24px 0'}}>Waiting for data…</div>}
          </Panel>

          <Panel title="🔮 Commit-Reveal Futures" accent={C.purple} glow={C.purple}
            tooltip="Agents commit to a future energy price by submitting a cryptographic hash (commit), then reveal the actual price later. If the revealed price deviates too much, their collateral deposit is slashed — preventing market manipulation."
            badge={futures?.stats&&<span style={{fontSize:10,color:C.purple,background:`${C.purple}10`,padding:'2px 7px',borderRadius:6,fontWeight:600}}>{futures.stats.total_contracts??0} contracts</span>}>
            {futures?.stats?(
              <>
                <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8,marginBottom:10}}>
                  {[{l:'Active',v:String(futures.stats.active_contracts??0),c:C.purple},{l:'Deposits',v:`$${(futures.stats.total_deposits_usd??0).toFixed(4)}`,c:C.yellow},{l:'Slashed',v:`$${(futures.stats.total_slashed_usd??0).toFixed(4)}`,c:C.red}].map((s,i)=>(
                    <div key={i} style={{background:'rgba(0,0,0,0.2)',borderRadius:9,padding:'9px 11px',textAlign:'center'}}>
                      <div style={{fontSize:17,fontWeight:700,color:s.c,fontFamily:"'Space Grotesk',ui-sans-serif"}}>{s.v}</div>
                      <div style={{fontSize:9,color:C.dimmer,marginTop:2,textTransform:'uppercase',letterSpacing:'0.05em'}}>{s.l}</div>
                    </div>
                  ))}
                </div>
                <div style={{maxHeight:180,overflowY:'auto',display:'flex',flexDirection:'column',gap:5}}>
                  {(futures.recent??[]).length===0
                    ?<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'14px 0'}}>Run simulation to see contracts</div>
                    :(futures.recent??[]).map((c:any,i:number)=>{
                      const sc:Record<string,string>={settled:C.green,slashed:C.red,committed:C.yellow,revealed:C.cyan,expired:C.dim}
                      const col=sc[c.state]??C.dim
                      return(
                        <motion.div key={i} initial={{opacity:0}} animate={{opacity:1}}
                          style={{background:'rgba(255,255,255,0.02)',border:`1px solid ${col}20`,borderRadius:9,padding:'7px 10px'}}>
                          <div style={{display:'flex',justifyContent:'space-between',marginBottom:3}}>
                            <span style={{fontSize:10,color:col,fontWeight:700,textTransform:'uppercase'}}>{c.state}</span>
                            <span style={{fontSize:10,color:C.dim}}>spread {((c.spread??0)*100).toFixed(1)}%</span>
                          </div>
                          <div style={{fontSize:10,color:`${C.text}60`}}>{c.producer} → {c.consumer} · ${(c.futures_price??0).toFixed(4)}/kWh</div>
                          {(c.slash_amount_usd??0)>0&&<div style={{fontSize:9,color:C.red,marginTop:2}}>Slashed: ${c.slash_amount_usd.toFixed(4)}</div>}
                        </motion.div>
                      )
                    })}
                </div>
              </>
            ):<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'24px 0'}}>Waiting for data…</div>}
          </Panel>
        </div>

        {/* GREEN CERTS + x402 */}
        <div style={{display:'grid',gridTemplateColumns:isMobile?'1fr':'1fr 1fr',gap:12,marginBottom:12}}>
          <Panel title="🌿 Renewable Energy Certificates" accent={C.green} glow={C.green}
            tooltip="Every kWh of solar energy traded generates a Renewable Energy Certificate (REC) recorded on-chain. This creates an immutable, auditable proof that the energy came from a clean source — replacing paper-based tracking systems.">
            {certs?.stats?(
              <>
                <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:8,marginBottom:10}}>
                  {[{l:'RECs',v:String(certs.stats.total_certificates??0),c:C.green},{l:'kWh',v:`${(certs.stats.total_kwh_certified??0).toFixed(1)}`,c:C.cyan},{l:'Green%',v:`${certs.stats.green_percentage??0}%`,c:C.green},{l:'Sources',v:String(certs.stats.unique_sources??0),c:C.purple}].map((s,i)=>(
                    <div key={i} style={{background:'rgba(0,0,0,0.2)',borderRadius:9,padding:'9px 11px',textAlign:'center'}}>
                      <div style={{fontSize:16,fontWeight:700,color:s.c,fontFamily:"'Space Grotesk',ui-sans-serif"}}>{s.v}</div>
                      <div style={{fontSize:9,color:C.dimmer,marginTop:2,textTransform:'uppercase',letterSpacing:'0.05em'}}>{s.l}</div>
                    </div>
                  ))}
                </div>
                <div style={{maxHeight:90,overflowY:'auto',display:'flex',flexDirection:'column',gap:3}}>
                  {(certs.recent??[]).slice(0,8).map((c:any,i:number)=>(
                    <div key={i} style={{display:'flex',justifyContent:'space-between',fontSize:10,color:C.dim,padding:'2px 0'}}>
                      <span style={{color:C.green}}>{c.source}</span>
                      <span>{(c.kwh??0).toFixed(3)} kWh</span>
                      <span style={{color:C.dimmer}}>T{c.tick}</span>
                    </div>
                  ))}
                </div>
              </>
            ):<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'24px 0'}}>Waiting for data…</div>}
          </Panel>

          <Panel title="💳 x402 Pay-as-you-go API" accent={C.yellow}
            tooltip="x402 is an emerging internet standard for machine-to-machine payments. Premium API endpoints require a tiny USDC micropayment per request — paid automatically by software, no human needed. This demonstrates the future of API monetization."
            badge={<span style={{fontSize:9,color:C.dimmer,fontStyle:'italic'}}>{x402?.simulation_mode?'Sim: format+replay validation':'Live: on-chain Arc verification'}</span>}>
            {x402?(
              <>
                <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:8,marginBottom:10}}>
                  {[{l:'Revenue',v:`$${(x402.total_revenue_usd??0).toFixed(5)}`,c:C.yellow},{l:'Total',v:String(x402.total_requests??0),c:C.cyan},{l:'Paid',v:String(x402.paid_requests??0),c:C.green},{l:'Rejected',v:String(x402.rejected_requests??0),c:C.red}].map((s,i)=>(
                    <div key={i} style={{background:'rgba(0,0,0,0.2)',borderRadius:9,padding:'9px 11px',textAlign:'center'}}>
                      <div style={{fontSize:14,fontWeight:700,color:s.c,fontFamily:"'Space Grotesk',ui-sans-serif"}}>{s.v}</div>
                      <div style={{fontSize:9,color:C.dimmer,marginTop:2,textTransform:'uppercase',letterSpacing:'0.05em'}}>{s.l}</div>
                    </div>
                  ))}
                </div>
                <div style={{fontSize:9,color:C.dimmer,marginBottom:6}}>Validation: {x402.validation??'format + replay-protection'}</div>
                {[{ep:'/api/economic-proof',cost:'$0.003'},{ep:'/api/schelling',cost:'$0.002'},{ep:'/api/certificates',cost:'$0.001'}].map((t,i)=>(
                  <div key={i} style={{display:'flex',justifyContent:'space-between',fontSize:10,color:C.dim,padding:'4px 0',borderBottom:`1px solid ${C.border}`}}>
                    <span style={{fontFamily:'monospace',color:C.purple}}>{t.ep}</span>
                    <span style={{color:C.yellow,fontWeight:600}}>{t.cost}</span>
                  </div>
                ))}
              </>
            ):<div style={{fontSize:11,color:C.dimmer,textAlign:'center',padding:'24px 0'}}>Waiting for data…</div>}
          </Panel>
        </div>

        {/* FAQ */}
        <FAQSection/>

      </div>
    </div>
  )
}
