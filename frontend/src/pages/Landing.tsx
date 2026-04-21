import React, { useRef, useState, useEffect, useCallback } from 'react'
import { motion, useScroll, useTransform } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import NeuralGrid from '../components/NeuralGrid'
import { useWindowWidth } from '../hooks/useWindowWidth'

const EASE = [0.22, 1, 0.36, 1] as const

const Reveal = ({
  children, delay = 0, y = 40,
}: { children: React.ReactNode; delay?: number; y?: number }) => (
  <motion.div
    initial={{ opacity: 0, y }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: '-60px' }}
    transition={{ duration: 0.8, delay, ease: EASE }}
  >
    {children}
  </motion.div>
)

function Counter({ to, suffix = '' }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0)
  const fired = useRef(false)
  return (
    <motion.span
      onViewportEnter={() => {
        if (fired.current) return
        fired.current = true
        let v = 0
        const step = to / 60
        const id = setInterval(() => {
          v += step
          if (v >= to) { setVal(to); clearInterval(id) } else setVal(Math.floor(v))
        }, 16)
      }}
    >{val.toLocaleString()}{suffix}</motion.span>
  )
}

const FeatureCard = ({ icon, tag, title, body }: { icon: string; tag: string; title: string; body: string }) => {
  const ref = useRef<HTMLDivElement>(null)
  const [tilt, setTilt] = useState({ x: 0, y: 0 })
  const onMove = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect()
    setTilt({ x: ((e.clientX - r.left) / r.width - 0.5) * 12, y: ((e.clientY - r.top) / r.height - 0.5) * -12 })
  }
  return (
    <motion.div ref={ref} onMouseMove={onMove} onMouseLeave={() => setTilt({ x: 0, y: 0 })}
      animate={{ rotateX: tilt.y, rotateY: tilt.x }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
      whileHover={{ y: -6 }}
      style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.07)', borderRadius: 22, padding: '28px 26px', transformStyle: 'preserve-3d', height: '100%', boxSizing: 'border-box' }}
    >
      <div style={{ fontSize: 28, marginBottom: 12 }}>{icon}</div>
      <div style={{ fontSize: 10, color: '#9B8CFF', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>{tag}</div>
      <h3 style={{ margin: '0 0 10px', fontSize: 16, color: '#fff', fontWeight: 600, lineHeight: 1.3 }}>{title}</h3>
      <p style={{ margin: 0, fontSize: 13.5, color: 'rgba(230,238,246,0.55)', lineHeight: 1.7 }}>{body}</p>
    </motion.div>
  )
}

const MARQUEE = [
  { icon: '⚡', label: 'Sub-cent fees' }, { icon: '🔗', label: 'Arc Testnet' }, { icon: '🤖', label: 'Agent-to-Agent' },
  { icon: '💵', label: 'USDC Settlement' }, { icon: '🔮', label: 'Commit-Reveal Futures' }, { icon: '🤝', label: 'Shapley Coalitions' },
  { icon: '🧠', label: 'Gemini AI Brain' }, { icon: '📜', label: 'Merkle Certificates' }, { icon: '⏱', label: '<1s Finality' }, { icon: '🛡', label: 'Slashing Mechanics' },
]

const Marquee = () => {
  const items = [...MARQUEE, ...MARQUEE]
  return (
    <div style={{ overflow: 'hidden', padding: '28px 0', borderTop: '1px solid rgba(255,255,255,0.05)', borderBottom: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.012)' }}>
      <motion.div animate={{ x: ['0%', '-50%'] }} transition={{ duration: 30, repeat: Infinity, ease: 'linear' }}
        style={{ display: 'flex', gap: 12, width: 'max-content' }}>
        {items.map((item, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 18px', borderRadius: 40, background: 'rgba(110,231,243,0.04)', border: '1px solid rgba(110,231,243,0.1)', backdropFilter: 'blur(8px)', whiteSpace: 'nowrap', fontSize: 13, color: 'rgba(230,238,246,0.7)', fontWeight: 500 }}>
            <span style={{ fontSize: 16 }}>{item.icon}</span>{item.label}
          </div>
        ))}
      </motion.div>
    </div>
  )
}

export default function Landing() {
  const nav = useNavigate()
  const heroRef = useRef<HTMLDivElement>(null)
  const glowRef = useRef<HTMLDivElement>(null)
  const w = useWindowWidth()
  const isMobile = w < 768
  const isTablet = w < 1024
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] })
  const heroY = useTransform(scrollYProgress, [0, 1], ['0%', '28%'])
  const heroOpacity = useTransform(scrollYProgress, [0, 0.75], [1, 0])

  const onMouse = useCallback((e: MouseEvent) => {
    if (glowRef.current) glowRef.current.style.transform = `translate(${e.clientX - 300}px, ${e.clientY - 300}px)`
  }, [])
  useEffect(() => { window.addEventListener('mousemove', onMouse); return () => window.removeEventListener('mousemove', onMouse) }, [onMouse])

  return (
    <div style={{ background: 'linear-gradient(180deg,#030c18 0%,#050f1e 40%,#060e1c 75%,#07101f 100%)', color: '#e6eef6', fontFamily: "'Inter',ui-sans-serif,system-ui", minHeight: '100vh', overflowX: 'hidden' }}>
      <div ref={glowRef} style={{ position: 'fixed', top: 0, left: 0, width: 600, height: 600, borderRadius: '50%', pointerEvents: 'none', zIndex: 0, background: 'radial-gradient(circle,rgba(110,231,243,0.04) 0%,transparent 65%)', transition: 'transform 0.12s ease', willChange: 'transform' }} />

      {/* Nav */}
      <motion.nav initial={{ opacity: 0, y: -16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: EASE }}
        style={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 200, height: 60, padding: `0 ${isMobile?16:32}px`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', backdropFilter: 'blur(24px)', background: 'rgba(3,12,24,0.75)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src="/gridmint-logo.svg" style={{ width: 32, height: 32 }} alt="GridMint" />
          <span style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontWeight: 700, fontSize: 17, letterSpacing: '-0.02em', color: '#fff' }}>GridMint</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile?8:16 }}>
          {!isMobile&&<motion.button 
            whileHover={{ scale: 1.05, y: -2, boxShadow: '0 8px 24px rgba(155,140,255,0.35)' }} 
            whileTap={{ scale: 0.95 }} 
            onClick={() => nav('/whitepaper')}
            style={{ 
              padding: '9px 20px', 
              borderRadius: 12, 
              background: 'linear-gradient(135deg, rgba(155,140,255,0.15) 0%, rgba(110,231,243,0.12) 100%)', 
              color: '#e6eef6', 
              fontWeight: 700, 
              fontSize: 13, 
              border: '1px solid rgba(155,140,255,0.35)', 
              cursor: 'pointer',
              backdropFilter: 'blur(10px)',
              boxShadow: '0 4px 16px rgba(155,140,255,0.15), inset 0 1px 0 rgba(255,255,255,0.1)',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              position: 'relative',
              overflow: 'hidden'
            }}>
            <span style={{ fontSize: 15 }}>📄</span>
            <span style={{ 
              background: 'linear-gradient(90deg, #9B8CFF 0%, #6EE7F3 100%)', 
              WebkitBackgroundClip: 'text', 
              WebkitTextFillColor: 'transparent',
              fontWeight: 700 
            }}>Whitepaper</span>
            <motion.div 
              animate={{ x: [-100, 300] }}
              transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100px',
                height: '100%',
                background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent)',
                pointerEvents: 'none'
              }}
            />
          </motion.button>}
          {!isMobile&&<span style={{ fontSize: 12, color: 'rgba(230,238,246,0.3)', fontWeight: 500 }}>Agentic Economy on Arc</span>}
          <motion.button whileHover={{ scale: 1.04, boxShadow: '0 0 30px rgba(110,231,243,0.3)' }} whileTap={{ scale: 0.97 }} onClick={() => nav('/dashboard')}
            style={{ padding: isMobile?'7px 14px':'8px 20px', borderRadius: 12, background: 'linear-gradient(90deg,#6EE7F3,#9B8CFF)', color: '#020e18', fontWeight: 700, fontSize: isMobile?12:13, border: 'none', cursor: 'pointer' }}>
            {isMobile?'Dashboard →':'Live Dashboard →'}
          </motion.button>
        </div>
      </motion.nav>

      {/* Hero */}
      <div ref={heroRef} style={{ position: 'relative', minHeight: '100vh', display: 'flex', alignItems: 'center', paddingTop: 60, overflow: 'hidden' }}>
        <motion.div animate={{ scale: [1,1.08,1], opacity: [0.5,0.85,0.5] }} transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
          style={{ position: 'absolute', top: '5%', left: '-5%', width: 700, height: 700, borderRadius: '50%', background: 'radial-gradient(circle,rgba(110,231,243,0.055) 0%,transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />
        <motion.div animate={{ scale: [1,1.06,1], opacity: [0.4,0.7,0.4] }} transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
          style={{ position: 'absolute', bottom: '5%', right: '-5%', width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle,rgba(155,140,255,0.055) 0%,transparent 65%)', pointerEvents: 'none', zIndex: 0 }} />

        <motion.div style={{ y: heroY, opacity: heroOpacity, width: '100%', position: 'relative', zIndex: 1 }}>
          <div style={{ maxWidth: 1160, margin: '0 auto', padding: `0 ${isMobile?16:32}px`, display: 'grid', gridTemplateColumns: isMobile?'1fr':'1fr 1fr', gap: isMobile?32:56, alignItems: 'center' }}>
            {/* Left */}
            <div>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15, duration: 0.6, ease: EASE }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 7, padding: '5px 14px', background: 'rgba(110,231,243,0.07)', border: '1px solid rgba(110,231,243,0.18)', borderRadius: 24, fontSize: 12, color: '#6EE7F3', marginBottom: 22, fontWeight: 600 }}>
                <motion.span animate={{ opacity: [1,0.3,1] }} transition={{ duration: 1.8, repeat: Infinity }}
                  style={{ width: 6, height: 6, borderRadius: '50%', background: '#6EE7F3', display: 'inline-block', boxShadow: '0 0 8px #6EE7F3' }} />
                Live on Arc Testnet
              </motion.div>
              <motion.h1 initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, duration: 0.75, ease: EASE }}
                style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontSize: 'clamp(34px,4.5vw,58px)', fontWeight: 700, letterSpacing: '-0.035em', lineHeight: 1.08, margin: '0 0 22px', color: '#fff' }}>
                The Agentic<br />
                <span style={{ background: 'linear-gradient(100deg,#6EE7F3 20%,#9B8CFF 80%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>Energy Economy</span>
              </motion.h1>
              <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4, duration: 0.65, ease: EASE }}
                style={{ fontSize: 16, color: 'rgba(230,238,246,0.58)', lineHeight: 1.75, maxWidth: 460, margin: '0 0 34px' }}>
                Autonomous solar, battery & consumer agents trade energy in real-time — settling every micro-transaction directly on-chain via Arc USDC. Sub-cent fees. Deterministic finality. Zero intermediaries.
              </motion.p>
              <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55, duration: 0.5, ease: EASE }}
                style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <motion.button whileHover={{ scale: 1.05, boxShadow: '0 20px 60px rgba(110,231,243,0.32)' }} whileTap={{ scale: 0.97 }} onClick={() => nav('/dashboard')}
                  style={{ padding: '14px 30px', borderRadius: 14, background: 'linear-gradient(90deg,#6EE7F3,#9B8CFF)', color: '#020e18', fontWeight: 700, fontSize: 15, border: 'none', cursor: 'pointer' }}>
                  Enter Live Dashboard →
                </motion.button>
                <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  onClick={() => document.getElementById('problem')?.scrollIntoView({ behavior: 'smooth' })}
                  style={{ padding: '14px 24px', borderRadius: 14, background: 'rgba(255,255,255,0.04)', color: '#e6eef6', fontWeight: 600, fontSize: 15, border: '1px solid rgba(255,255,255,0.09)', cursor: 'pointer' }}>
                  See the proof ↓
                </motion.button>
              </motion.div>
            </div>

            {/* Right — NeuralGrid (hidden on mobile) */}
            {!isMobile&&<motion.div initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.45, duration: 0.85, ease: EASE }} style={{ position: 'relative' }}>
              <div style={{ borderRadius: 24, overflow: 'hidden', border: '1px solid rgba(110,231,243,0.1)', boxShadow: '0 40px 100px rgba(2,8,20,0.7), inset 0 1px 0 rgba(255,255,255,0.06)', background: 'rgba(3,12,22,0.6)', backdropFilter: 'blur(4px)' }}>
                <NeuralGrid width={520} height={380} />
              </div>
              {[
                { label: 'Trades/tick', value: '5–15', color: '#6EE7F3', pos: { top: '8%', left: '-10%' } },
                { label: 'Avg fee', value: '<$0.001', color: '#4ade80', pos: { top: '55%', right: '-10%' } },
                { label: 'Settlement', value: '<1 sec', color: '#9B8CFF', pos: { bottom: '10%', left: '6%' } },
              ].map((pill, i) => (
                <motion.div key={i} initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.9 + i * 0.15, ease: EASE }}
                  style={{ position: 'absolute', ...pill.pos, background: 'rgba(3,13,26,0.88)', backdropFilter: 'blur(12px)', border: `1px solid ${pill.color}30`, borderRadius: 12, padding: '8px 14px', pointerEvents: 'none', zIndex: 10 }}>
                  <div style={{ fontSize: 10, color: 'rgba(230,238,246,0.45)', marginBottom: 2 }}>{pill.label}</div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: pill.color, fontFamily: "'Space Grotesk',ui-sans-serif" }}>{pill.value}</div>
                </motion.div>
              ))}
            </motion.div>}
          </div>
        </motion.div>

        <motion.div animate={{ y: [0,8,0] }} transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
          style={{ position: 'absolute', bottom: 28, left: '50%', transform: 'translateX(-50%)', color: 'rgba(230,238,246,0.2)', fontSize: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, zIndex: 2 }}>
          <span>scroll to explore</span><span style={{ fontSize: 16 }}>↓</span>
        </motion.div>
      </div>

      <Marquee />

      {/* Stats */}
      <div style={{ padding: `${isMobile?36:56}px ${isMobile?16:32}px` }}>
        <div style={{ maxWidth: 1160, margin: '0 auto', display: 'grid', gridTemplateColumns: isMobile?'repeat(2,1fr)':'repeat(4,1fr)', gap: isMobile?0:2 }}>
          {[
            { display: null, raw: 50, suffix: '+', label: 'On-chain txns (demo)' },
            { display: '≤$0.001', raw: 0, suffix: '', label: 'Avg cost per trade' },
            { display: null, raw: 99, suffix: '%', label: 'Savings vs ETH gas' },
            { display: '<1s', raw: 0, suffix: '', label: 'Settlement finality' },
          ].map((s, i) => (
            <Reveal key={i} delay={i * 0.1}>
              <div style={{ padding: '28px 20px', borderLeft: i > 0 ? '1px solid rgba(255,255,255,0.05)' : undefined, textAlign: 'center' }}>
                <div style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontSize: 44, fontWeight: 700, color: '#fff', letterSpacing: '-0.03em', lineHeight: 1 }}>
                  {s.display ? s.display : <><Counter to={s.raw} />{s.suffix}</>}
                </div>
                <div style={{ fontSize: 13, color: 'rgba(230,238,246,0.38)', marginTop: 8 }}>{s.label}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>

      {/* Problem */}
      <div id="problem" style={{ padding: `${isMobile?48:80}px ${isMobile?16:32}px`, background: 'rgba(0,0,0,0.15)' }}>
        <div style={{ maxWidth: 1160, margin: '0 auto' }}>
          <Reveal>
            <div style={{ textAlign: 'center', marginBottom: isMobile?36:64 }}>
              <div style={{ fontSize: 11, color: '#6EE7F3', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14 }}>The Core Problem</div>
              <h2 style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontSize: 'clamp(22px,3.5vw,42px)', fontWeight: 700, letterSpacing: '-0.025em', color: '#fff', margin: '0 auto', maxWidth: 660, lineHeight: 1.15 }}>High-frequency value transfer was mathematically impossible</h2>
            </div>
          </Reveal>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile?'1fr':'1fr 1fr', gap: 24, marginBottom: 32 }}>
            <Reveal delay={0.1}>
              <div style={{ padding: '28px', background: 'rgba(255,60,60,0.04)', border: '1px solid rgba(255,60,60,0.1)', borderRadius: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                  <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#f87171' }} />
                  <div style={{ fontSize: 12, color: '#f87171', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Ethereum — Traditional Gas</div>
                </div>
                <div style={{ fontFamily: 'monospace', fontSize: 14, color: 'rgba(230,238,246,0.55)', lineHeight: 2.2, background: 'rgba(0,0,0,0.2)', borderRadius: 12, padding: '16px 20px' }}>
                  <div>Trade value:   <span style={{ color: '#e6eef6' }}>$0.003</span></div>
                  <div>Gas cost:      <span style={{ color: '#f87171' }}>$5.00 – $50.00</span></div>
                  <div>Net margin:    <span style={{ color: '#f87171', fontWeight: 700 }}>-166,566%</span></div>
                  <div style={{ marginTop: 8, color: '#f87171', fontSize: 12 }}>→ Economically impossible at scale</div>
                </div>
              </div>
            </Reveal>
            <Reveal delay={0.2}>
              <div style={{ padding: '28px', background: 'rgba(110,231,243,0.03)', border: '1px solid rgba(110,231,243,0.12)', borderRadius: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
                  <motion.div animate={{ opacity: [1,0.4,1] }} transition={{ duration: 1.5, repeat: Infinity }}
                    style={{ width: 10, height: 10, borderRadius: '50%', background: '#6EE7F3', boxShadow: '0 0 8px #6EE7F3' }} />
                  <div style={{ fontSize: 12, color: '#6EE7F3', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Arc + Circle USDC</div>
                </div>
                <div style={{ fontFamily: 'monospace', fontSize: 14, color: 'rgba(230,238,246,0.55)', lineHeight: 2.2, background: 'rgba(0,0,0,0.2)', borderRadius: 12, padding: '16px 20px' }}>
                  <div>Trade value:   <span style={{ color: '#e6eef6' }}>$0.003</span></div>
                  <div>Settlement:    <span style={{ color: '#6EE7F3' }}>&lt;$0.0001 (sub-cent)</span></div>
                  <div>Net margin:    <span style={{ color: '#6EE7F3', fontWeight: 700 }}>+97% retained</span></div>
                  <div style={{ marginTop: 8, color: '#6EE7F3', fontSize: 12 }}>→ 50,000× cheaper than Ethereum</div>
                </div>
              </div>
            </Reveal>
          </div>
          <Reveal delay={0.3}>
            <p style={{ textAlign: 'center', fontSize: 15, color: 'rgba(230,238,246,0.42)', maxWidth: 700, margin: '0 auto', lineHeight: 1.75 }}>
              Arc's stablecoin-native architecture eliminates gas volatility entirely. Every agent trade settles in USDC with sub-second deterministic finality — unlocking the Agentic Economy at any transaction size.
            </p>
          </Reveal>
        </div>
      </div>

      {/* CTA band */}
      <div style={{ padding: `${isMobile?48:72}px ${isMobile?16:32}px` }}>
        <div style={{ maxWidth: 1160, margin: '0 auto' }}>
          <Reveal>
            <motion.div whileHover={{ boxShadow: '0 0 100px rgba(110,231,243,0.07)' }}
              style={{ display: 'grid', gridTemplateColumns: isMobile?'1fr':'1fr auto', gap: isMobile?24:40, alignItems: 'center', padding: isMobile?'28px 24px':'44px 52px', background: 'linear-gradient(135deg,rgba(110,231,243,0.05),rgba(155,140,255,0.05))', border: '1px solid rgba(110,231,243,0.1)', borderRadius: 28 }}>
              <div>
                <div style={{ fontSize: 11, color: '#9B8CFF', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 14 }}>Live Demo</div>
                <h3 style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontSize: 32, fontWeight: 700, letterSpacing: '-0.02em', color: '#fff', margin: '0 0 12px', lineHeight: 1.2 }}>Watch autonomous agents settle USDC in real-time</h3>
                <p style={{ margin: 0, fontSize: 15, color: 'rgba(230,238,246,0.5)', lineHeight: 1.65, maxWidth: 480 }}>10 agents (3 solar, 5 consumers, 2 batteries). Uniform-price auctions every 3 seconds. Every trade verifiable on <a href="https://testnet.arcscan.app" target="_blank" rel="noreferrer" style={{ color: '#6EE7F3', textDecoration: 'none' }}>ArcScan ↗</a>.</p>
              </div>
              <motion.button whileHover={{ scale: 1.06, boxShadow: '0 24px 80px rgba(110,231,243,0.35)' }} whileTap={{ scale: 0.96 }} onClick={() => nav('/dashboard')}
                style={{ padding: '16px 36px', borderRadius: 16, background: 'linear-gradient(90deg,#6EE7F3,#9B8CFF)', color: '#020e18', fontWeight: 700, fontSize: 16, border: 'none', cursor: 'pointer', whiteSpace: 'nowrap' }}>
                Open Dashboard →
              </motion.button>
            </motion.div>
          </Reveal>
        </div>
      </div>

      {/* Features */}
      <div style={{ padding: `${isMobile?48:80}px ${isMobile?16:32}px`, background: 'rgba(0,0,0,0.12)' }}>
        <div style={{ maxWidth: 1160, margin: '0 auto' }}>
          <Reveal>
            <div style={{ textAlign: 'center', marginBottom: isMobile?36:56 }}>
              <div style={{ fontSize: 11, color: '#9B8CFF', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14 }}>The GridMint Solution</div>
              <h2 style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontSize: 'clamp(22px,3.5vw,42px)', fontWeight: 700, letterSpacing: '-0.025em', color: '#fff', margin: 0 }}>Four breakthrough layers</h2>
            </div>
          </Reveal>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile?'1fr':isTablet?'1fr':'repeat(2,1fr)', gap: 16 }}>
            {[
              { icon: '⚡', tag: 'Core Market', title: 'Uniform-Price Auction Engine', body: 'Every 3-second tick, solar sellers and battery dischargers submit offers. A merit-order clearing algorithm matches supply and demand at a single uniform price — maximizing social welfare.' },
              { icon: '🤝', tag: 'Game Theory', title: 'Shapley Coalition Splitting', body: 'Agents form coalitions to pool capacity. Revenue is split using exact Shapley values — guaranteeing fair, game-theoretically optimal compensation for every contributor.' },
              { icon: '🔮', tag: 'Incentive Design', title: 'Commit-Reveal Futures', body: 'Agents stake USDC to commit to future supply/demand forecasts. Accurate predictions earn yield; deviations trigger automatic slashing — aligning incentives for honest reporting.' },
              { icon: '🔗', tag: 'Arc + Circle', title: 'On-Chain USDC Settlement', body: 'Every matched trade settles directly on Arc testnet via Circle USDC transfers. A Merkle-backed certificate ledger provides cryptographic proof of green energy provenance.' },
            ].map((card, i) => (
              <Reveal key={i} delay={i * 0.1}><FeatureCard {...card} /></Reveal>
            ))}
          </div>
        </div>
      </div>

      {/* Architecture */}
      <div style={{ padding: `${isMobile?48:80}px ${isMobile?16:32}px` }}>
        <div style={{ maxWidth: 1160, margin: '0 auto' }}>
          <Reveal>
            <div style={{ textAlign: 'center', marginBottom: 48 }}>
              <div style={{ fontSize: 11, color: '#6EE7F3', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 14 }}>Architecture</div>
              <h2 style={{ fontFamily: "'Space Grotesk',ui-sans-serif", fontSize: isMobile?24:36, fontWeight: 700, letterSpacing: '-0.025em', color: '#fff', margin: 0 }}>Fully autonomous, fully on-chain</h2>
            </div>
          </Reveal>
          <div style={{ display: 'grid', gridTemplateColumns: isMobile?'1fr':isTablet?'repeat(2,1fr)':'repeat(3,1fr)', gap: 12 }}>
            {[
              { tag: 'Arc Testnet', desc: 'L1 USDC settlement, sub-cent fees, <1s finality', color: '#6EE7F3' },
              { tag: 'Circle Nanopayments', desc: 'Programmable USDC transfers per micro-trade', color: '#4ade80' },
              { tag: 'FastAPI + WebSocket', desc: 'Real-time tick stream; live dashboard at 3s cadence', color: '#6EE7F3' },
              { tag: 'Gemini 2.5 AI Brain', desc: 'Market narration, battery dispatch, query console', color: '#9B8CFF' },
              { tag: 'MWU Schelling Points', desc: 'Price distribution learning per agent via online MWU', color: '#9B8CFF' },
              { tag: 'x402 Paywall', desc: 'Per-API monetization on every premium endpoint', color: '#facc15' },
            ].map((item, i) => (
              <Reveal key={i} delay={i * 0.07}>
                <motion.div whileHover={{ y: -4, background: 'rgba(255,255,255,0.035)' }}
                  style={{ padding: '18px 20px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.055)', borderRadius: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: item.color, marginBottom: 7, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{item.tag}</div>
                  <div style={{ fontSize: 13, color: 'rgba(230,238,246,0.48)', lineHeight: 1.6 }}>{item.desc}</div>
                </motion.div>
              </Reveal>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid rgba(255,255,255,0.05)', padding: '28px 32px' }}>
        <div style={{ maxWidth: 1160, margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <img src="/assets/arc_icon.svg" style={{ width: 18, height: 18, opacity: 0.4 }} alt="" />
            <span style={{ fontSize: 13, color: 'rgba(230,238,246,0.28)' }}>GridMint — Agentic Economy on Arc</span>
          </div>
          <span style={{ fontSize: 12, color: 'rgba(230,238,246,0.18)' }}>Hackathon · April 2026</span>
        </div>
      </footer>
    </div>
  )
}
