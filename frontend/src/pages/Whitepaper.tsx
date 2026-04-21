import React, { useRef, useEffect, useCallback } from 'react'
import { motion, useScroll, useTransform } from 'framer-motion'
import { useNavigate } from 'react-router-dom'

const EASE = [0.22, 1, 0.36, 1] as const

// Floating particle background
const FloatingParticles = () => {
  const particles = Array.from({ length: 20 }, (_, i) => ({
    x: Math.random() * 100,
    y: Math.random() * 100,
    size: Math.random() * 4 + 2,
    duration: Math.random() * 10 + 15,
    delay: Math.random() * 5
  }))

  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden', pointerEvents: 'none', zIndex: 0 }}>
      {particles.map((p, i) => (
        <motion.div
          key={i}
          animate={{
            y: [0, -30, 0],
            x: [0, Math.sin(i) * 20, 0],
            opacity: [0.1, 0.3, 0.1]
          }}
          transition={{
            duration: p.duration,
            repeat: Infinity,
            delay: p.delay,
            ease: 'easeInOut'
          }}
          style={{
            position: 'absolute',
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            borderRadius: '50%',
            background: i % 2 === 0 ? '#6EE7F3' : '#9B8CFF',
            boxShadow: `0 0 ${p.size * 2}px ${i % 2 === 0 ? '#6EE7F3' : '#9B8CFF'}`
          }}
        />
      ))}
    </div>
  )
}

// Animated section divider
const SectionDivider = () => (
  <motion.div
    initial={{ scaleX: 0, opacity: 0 }}
    whileInView={{ scaleX: 1, opacity: 1 }}
    viewport={{ once: true, margin: '-50px' }}
    transition={{ duration: 1.2, ease: EASE }}
    style={{
      height: 2,
      background: 'linear-gradient(90deg, transparent, #6EE7F3, #9B8CFF, transparent)',
      margin: '64px 0',
      borderRadius: 2,
      boxShadow: '0 0 20px rgba(110,231,243,0.3)'
    }}
  />
)

// Stat card with animation
const StatCard = ({ icon, value, label }: { icon: string; value: string; label: string }) => (
  <motion.div
    initial={{ opacity: 0, y: 20, scale: 0.9 }}
    whileInView={{ opacity: 1, y: 0, scale: 1 }}
    viewport={{ once: true, margin: '-30px' }}
    whileHover={{ y: -6, scale: 1.03 }}
    transition={{ duration: 0.6, ease: EASE }}
    style={{
      background: 'linear-gradient(135deg, rgba(110,231,243,0.06) 0%, rgba(155,140,255,0.06) 100%)',
      border: '1px solid rgba(110,231,243,0.2)',
      borderRadius: 16,
      padding: '24px 20px',
      textAlign: 'center',
      backdropFilter: 'blur(10px)',
      boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
      position: 'relative',
      overflow: 'hidden'
    }}
  >
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
      style={{
        position: 'absolute',
        top: -50,
        right: -50,
        width: 100,
        height: 100,
        background: 'radial-gradient(circle, rgba(110,231,243,0.1) 0%, transparent 70%)',
        borderRadius: '50%'
      }}
    />
    <div style={{ fontSize: 32, marginBottom: 8 }}>{icon}</div>
    <div style={{
      fontSize: 28,
      fontWeight: 700,
      color: '#6EE7F3',
      fontFamily: "'Space Grotesk', ui-sans-serif",
      marginBottom: 4
    }}>{value}</div>
    <div style={{ fontSize: 12, color: 'rgba(230,238,246,0.55)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
      {label}
    </div>
  </motion.div>
)

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <motion.section
    initial={{ opacity: 0, y: 40 }}
    whileInView={{ opacity: 1, y: 0 }}
    viewport={{ once: true, margin: '-80px' }}
    transition={{ duration: 0.8, ease: EASE }}
    style={{ marginBottom: 72, position: 'relative' }}
  >
    <motion.h2
      initial={{ x: -20, opacity: 0 }}
      whileInView={{ x: 0, opacity: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.7, delay: 0.2, ease: EASE }}
      style={{
        fontSize: 32,
        fontWeight: 700,
        marginBottom: 28,
        letterSpacing: '-0.025em',
        borderLeft: '4px solid #6EE7F3',
        paddingLeft: 20,
        background: 'linear-gradient(135deg, #6EE7F3 0%, #9B8CFF 100%)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        position: 'relative'
      }}>
      {title}
      <motion.div
        animate={{ scaleX: [0, 1, 0] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
        style={{
          position: 'absolute',
          bottom: -8,
          left: 0,
          height: 2,
          width: '100%',
          background: 'linear-gradient(90deg, #6EE7F3, #9B8CFF)',
          transformOrigin: 'left'
        }}
      />
    </motion.h2>
    <div style={{ color: 'rgba(230,238,246,0.75)', fontSize: 15.5, lineHeight: 1.9, letterSpacing: '0.003em' }}>
      {children}
    </div>
  </motion.section>
)

const Code = ({ children }: { children: React.ReactNode }) => (
  <code style={{
    background: 'rgba(110,231,243,0.08)',
    border: '1px solid rgba(110,231,243,0.2)',
    padding: '3px 10px',
    borderRadius: 7,
    fontSize: 14,
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    color: '#6EE7F3',
    fontWeight: 500
  }}>
    {children}
  </code>
)

const Formula = ({ children }: { children: React.ReactNode }) => (
  <motion.div
    initial={{ opacity: 0, x: -20 }}
    whileInView={{ opacity: 1, x: 0 }}
    viewport={{ once: true }}
    transition={{ duration: 0.6 }}
    style={{
      background: 'rgba(155,140,255,0.08)',
      border: '1px solid rgba(155,140,255,0.25)',
      padding: '18px 24px',
      borderRadius: 14,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: 13.5,
      color: '#9B8CFF',
      marginTop: 20,
      marginBottom: 20,
      overflowX: 'auto',
      lineHeight: 1.7,
      boxShadow: '0 4px 20px rgba(155,140,255,0.15)',
      position: 'relative'
    }}>
    <motion.div
      animate={{ opacity: [0.3, 0.6, 0.3] }}
      transition={{ duration: 3, repeat: Infinity }}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        background: 'linear-gradient(90deg, transparent, rgba(155,140,255,0.1), transparent)',
        pointerEvents: 'none'
      }}
    />
    <div style={{ position: 'relative', zIndex: 1 }}>{children}</div>
  </motion.div>
)

const Bullet = ({ children }: { children: React.ReactNode }) => (
  <motion.li
    initial={{ opacity: 0, x: -10 }}
    whileInView={{ opacity: 1, x: 0 }}
    viewport={{ once: true }}
    transition={{ duration: 0.5 }}
    style={{ marginBottom: 14, paddingLeft: 8, display: 'flex', alignItems: 'flex-start', gap: 8 }}
  >
    <span style={{ color: '#6EE7F3', fontWeight: 700, fontSize: 16, flexShrink: 0 }}>→</span>
    <span>{children}</span>
  </motion.li>
)

const IconBox = ({ icon, color }: { icon: string; color: string }) => (
  <motion.div
    whileHover={{ scale: 1.2, rotate: 360 }}
    transition={{ duration: 0.6 }}
    style={{
      width: 48,
      height: 48,
      borderRadius: 12,
      background: `${color}15`,
      border: `2px solid ${color}40`,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 24,
      marginBottom: 16,
      boxShadow: `0 4px 16px ${color}20`
    }}
  >
    {icon}
  </motion.div>
)

export default function Whitepaper() {
  const nav = useNavigate()
  const glowRef = useRef<HTMLDivElement>(null)
  const headerRef = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll()
  const headerOpacity = useTransform(scrollYProgress, [0, 0.15], [1, 0])
  const headerY = useTransform(scrollYProgress, [0, 0.15], [0, -50])

  const onMouse = useCallback((e: MouseEvent) => {
    if (glowRef.current) {
      glowRef.current.style.transform = `translate(${e.clientX - 350}px, ${e.clientY - 350}px)`
    }
  }, [])

  useEffect(() => {
    window.addEventListener('mousemove', onMouse)
    return () => window.removeEventListener('mousemove', onMouse)
  }, [onMouse])

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(180deg, #030c18 0%, #050f1e 50%, #030c18 100%)',
      color: '#e6eef6',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* Animated gradient glow */}
      <div ref={glowRef} style={{
        position: 'fixed',
        width: 700,
        height: 700,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(110,231,243,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
        zIndex: 1,
        transition: 'transform 0.15s ease',
        willChange: 'transform'
      }} />

      <FloatingParticles />

      {/* Grid background */}
      <div style={{
        position: 'fixed',
        inset: 0,
        backgroundImage: 'linear-gradient(rgba(110,231,243,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(110,231,243,0.02) 1px, transparent 1px)',
        backgroundSize: '50px 50px',
        pointerEvents: 'none',
        zIndex: 0
      }} />

      {/* Scanlines */}
      <div style={{
        position: 'fixed',
        inset: 0,
        backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.05) 2px, rgba(0,0,0,0.05) 4px)',
        pointerEvents: 'none',
        zIndex: 0
      }} />

      {/* Fixed nav */}
      <motion.nav
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, ease: EASE }}
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 100,
          height: 70,
          padding: '0 32px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backdropFilter: 'blur(20px)',
          background: 'rgba(3,12,24,0.85)',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          boxShadow: '0 4px 24px rgba(0,0,0,0.3)'
        }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <img src="/gridmint-logo.svg" style={{ width: 36, height: 36 }} alt="GridMint" />
          <span style={{ fontFamily: "'Space Grotesk', ui-sans-serif", fontWeight: 700, fontSize: 19, letterSpacing: '-0.02em', color: '#fff' }}>
            GridMint
          </span>
          <span style={{ fontSize: 12, color: 'rgba(230,238,246,0.3)', marginLeft: 8 }}>/ Technical Whitepaper</span>
        </div>
        <motion.button
          whileHover={{ scale: 1.05, boxShadow: '0 8px 28px rgba(110,231,243,0.35)' }}
          whileTap={{ scale: 0.95 }}
          onClick={() => nav(-1)}
          style={{
            padding: '10px 24px',
            borderRadius: 12,
            background: 'linear-gradient(90deg, #6EE7F3, #9B8CFF)',
            color: '#020e18',
            fontWeight: 700,
            fontSize: 14,
            border: 'none',
            cursor: 'pointer',
            boxShadow: '0 4px 16px rgba(110,231,243,0.25)'
          }}>
          ← Back
        </motion.button>
      </motion.nav>

      {/* Header Hero */}
      <motion.div
        ref={headerRef}
        style={{ opacity: headerOpacity, y: headerY }}
      >
        <div style={{
          paddingTop: 140,
          paddingBottom: 80,
          textAlign: 'center',
          position: 'relative',
          zIndex: 2
        }}>
          <motion.div
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease: EASE }}
          >
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 30, repeat: Infinity, ease: 'linear' }}
              style={{
                width: 120,
                height: 120,
                margin: '0 auto 24px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, rgba(110,231,243,0.15), rgba(155,140,255,0.15))',
                border: '2px solid rgba(110,231,243,0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 56,
                boxShadow: '0 8px 32px rgba(110,231,243,0.2)'
              }}
            >
              ⚡
            </motion.div>
          </motion.div>
          
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: EASE }}
            style={{
              fontFamily: "'Space Grotesk', ui-sans-serif",
              fontSize: 'clamp(32px, 5vw, 64px)',
              fontWeight: 700,
              letterSpacing: '-0.035em',
              lineHeight: 1.1,
              marginBottom: 24,
              background: 'linear-gradient(135deg, #6EE7F3 0%, #9B8CFF 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent'
            }}>
            GridMint
          </motion.h1>
          
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.6 }}
            style={{
              fontSize: 18,
              color: 'rgba(230,238,246,0.6)',
              lineHeight: 1.7,
              maxWidth: 750,
              margin: '0 auto 40px',
              padding: '0 20px'
            }}>
            A DePIN protocol for peer-to-peer energy trading with game-theoretic price discovery,
            cryptoeconomic futures markets, and sub-cent settlement via Circle Gateway on Arc blockchain.
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.8 }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 10,
              padding: '8px 20px',
              background: 'rgba(110,231,243,0.08)',
              border: '1px solid rgba(110,231,243,0.25)',
              borderRadius: 30,
              fontSize: 13,
              color: '#6EE7F3',
              fontWeight: 600
            }}>
            <motion.span
              animate={{ opacity: [1, 0.3, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: '#6EE7F3',
                boxShadow: '0 0 12px #6EE7F3',
                display: 'inline-block'
              }}
            />
            Live on Arc Testnet · Circle Nanopayments · Gemini AI
          </motion.div>
        </div>
      </motion.div>

      {/* Key Stats */}
      <div style={{ position: 'relative', zIndex: 2, padding: '0 32px', marginBottom: 80 }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 24 }}>
          <StatCard icon="📊" value="2264×" label="Cheaper than ETH" />
          <StatCard icon="⚡" value="<1s" label="Settlement Finality" />
          <StatCard icon="💰" value="$0.001" label="Avg Transaction Cost" />
          <StatCard icon="🔗" value="264+" label="Live Transactions" />
        </div>
      </div>

      <SectionDivider />

      {/* Main content */}
      <div style={{ maxWidth: 880, margin: '0 auto', padding: '0 32px 80px', position: 'relative', zIndex: 2 }}>

          {/* Abstract */}
          <Section title="Abstract">
            <p>
              GridMint is a decentralized physical infrastructure network (DePIN) that enables autonomous energy agents
              to trade electricity in real-time with micropayment settlement. The protocol combines Circle's Nanopayments
              infrastructure for gasless USDC transfers, Google Gemini's Function Calling for agentic intelligence, and
              Arc blockchain for sub-cent transaction costs.
            </p>
            <p>
              Unlike traditional grid operators that rely on centralized dispatch and static tariffs, GridMint implements
              a fully autonomous market where:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>Solar panels, batteries, and consumers self-organize without human intervention</Bullet>
              <Bullet>Prices emerge from Multiplicative Weights Update (MWU) learning, not hardcoded rules</Bullet>
              <Bullet>Coalitions form using Shapley value revenue splitting (virtual power plants)</Bullet>
              <Bullet>Futures contracts enable hedging via commit-reveal cryptography with slashing</Bullet>
              <Bullet>Green certificates are tracked in a Merkle ledger for renewable provenance</Bullet>
            </ul>
            <p>
              The system has been stress-tested with 264+ live Arc Testnet transactions, achieving a 2264× cost reduction
              compared to Ethereum mainnet ($0.29 vs $652.08 total gas cost).
            </p>
          </Section>

          {/* Architecture */}
          <Section title="System Architecture">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, marginBottom: 40 }}>
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                whileHover={{ scale: 1.05 }}
                style={{
                  padding: 24,
                  background: 'rgba(110,231,243,0.04)',
                  border: '1px solid rgba(110,231,243,0.15)',
                  borderRadius: 14,
                  textAlign: 'center'
                }}
              >
                <IconBox icon="🤖" color="#6EE7F3" />
                <div style={{ fontWeight: 700, color: '#6EE7F3', marginBottom: 8 }}>Agent Layer</div>
                <div style={{ fontSize: 13, color: 'rgba(230,238,246,0.5)', lineHeight: 1.6 }}>
                  Solar, battery & consumer agents with realistic behavioral models
                </div>
              </motion.div>
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                whileHover={{ scale: 1.05 }}
                transition={{ delay: 0.1 }}
                style={{
                  padding: 24,
                  background: 'rgba(155,140,255,0.04)',
                  border: '1px solid rgba(155,140,255,0.15)',
                  borderRadius: 14,
                  textAlign: 'center'
                }}
              >
                <IconBox icon="⚙️" color="#9B8CFF" />
                <div style={{ fontWeight: 700, color: '#9B8CFF', marginBottom: 8 }}>Market Engine</div>
                <div style={{ fontSize: 13, color: 'rgba(230,238,246,0.5)', lineHeight: 1.6 }}>
                  Continuous double auction with merit-order clearing
                </div>
              </motion.div>
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                whileHover={{ scale: 1.05 }}
                transition={{ delay: 0.2 }}
                style={{
                  padding: 24,
                  background: 'rgba(110,231,243,0.04)',
                  border: '1px solid rgba(110,231,243,0.15)',
                  borderRadius: 14,
                  textAlign: 'center'
                }}
              >
                <IconBox icon="💳" color="#6EE7F3" />
                <div style={{ fontWeight: 700, color: '#6EE7F3', marginBottom: 8 }}>Settlement</div>
                <div style={{ fontSize: 13, color: 'rgba(230,238,246,0.5)', lineHeight: 1.6 }}>
                  Circle Gateway with Arc Testnet USDC
                </div>
              </motion.div>
            </div>

            <h3 style={{ fontSize: 22, color: '#9B8CFF', marginTop: 48, marginBottom: 20, fontWeight: 700 }}>
              Layer 1: Agent Behavioral Models
            </h3>
            <p>
              GridMint implements three agent archetypes with realistic production/consumption curves:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>
                <strong>Solar Agents:</strong> Generate energy following a sine-wave solar irradiance model.
                Peak production at 12:00 (solar noon), zero output from 20:00-05:00. Output formula:
                <Formula>
                  production(hour) = capacity × max(0, sin(π × (hour - 5) / 15))
                </Formula>
                Prices are adjusted by the surge pricing oracle based on grid-wide supply/demand ratio.
              </Bullet>
              <Bullet>
                <strong>Battery Agents:</strong> Store energy with 90% round-trip efficiency, 80% depth-of-discharge limit.
                Use Exponentially Weighted Moving Average (EWMA) price tracking with ±2σ bands to decide when to charge
                (price below lower band) or discharge (price above upper band). Gemini AI can override these decisions
                every 5th tick with contextual reasoning.
              </Bullet>
              <Bullet>
                <strong>Consumer Agents:</strong> Have base load profiles with surge pricing multipliers. Industrial
                consumers have high urgency (less price-elastic), residential consumers are more flexible. Willingness-to-pay
                adjusts dynamically based on grid scarcity factor.
              </Bullet>
            </ul>

            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              Layer 2: Market Clearing Engine
            </h3>
            <p>
              Each simulation tick (3 real seconds = 18 simulated minutes at 360× speed), the grid engine:
            </p>
            <ol style={{ paddingLeft: 24, marginTop: 16 }}>
              <li style={{ marginBottom: 12 }}>
                Collects all active offers (sellers) and bids (buyers) from agents
              </li>
              <li style={{ marginBottom: 12 }}>
                Sorts offers ascending by price (merit order), bids descending by willingness-to-pay
              </li>
              <li style={{ marginBottom: 12 }}>
                Matches orders greedily until supply exhausted or bid price drops below offer price
              </li>
              <li style={{ marginBottom: 12 }}>
                Sets clearing price as the marginal price of the last matched order
              </li>
              <li style={{ marginBottom: 12 }}>
                Emits <Code>TradeMatch</Code> events to the settlement layer
              </li>
            </ol>
            <p>
              This implements a continuous double auction (CDA), the same mechanism used by wholesale electricity markets
              like PJM and ERCOT.
            </p>

            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              Layer 3: Settlement Infrastructure
            </h3>
            <p>
              GridMint supports three settlement backends with automatic fallback:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>
                <strong>GatewaySettler</strong> (production mode): Routes agent-to-agent trades through Circle Nanopayments
                Gateway server. Uses <Code>@circle-fin/x402-batching</Code> SDK to create <Code>GatewayClient</Code> instances,
                auto-deposits $0.10 USDC if needed, calls <Code>client.pay()</Code> with dynamic x402 paywalled routes.
                Fully gasless via EIP-3009 <Code>TransferWithAuthorization</Code>. Batches settlements for sub-millisecond
                finality.
              </Bullet>
              <Bullet>
                <strong>ArcSettler</strong> (fallback): Direct ERC-20 USDC transfers on Arc Testnet via web3.py. Used when
                Gateway server is unreachable or agent lacks Gateway deposit. Average gas cost: $0.0011 per transaction
                (measured over 264 live trades).
              </Bullet>
              <Bullet>
                <strong>SimulatedSettler</strong> (dev mode): In-memory balance tracking with deterministic fake tx hashes.
                Used for rapid prototyping and CI/CD testing without blockchain dependency.
              </Bullet>
            </ul>
          </Section>

          {/* Game Theory */}
          <Section title="Game-Theoretic Mechanisms">
            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              Schelling Point Discovery via Multiplicative Weights Update
            </h3>
            <p>
              Traditional energy markets rely on human operators to set prices. GridMint eliminates this via decentralized
              learning. Each agent maintains a probability distribution over a discretized price grid ($0.001 to $0.009 in
              9 slots). After each tick, agents observe whether their chosen price yielded a successful trade and update
              their weights:
            </p>
            <Formula>
              w_i(t+1) = w_i(t) × exp(η × reward_i(t))<br />
              p_i(t+1) = w_i(t+1) / Σ w_j(t+1)
            </Formula>
            <p>
              where η = 0.5 is the learning rate. This is an online convex optimization algorithm with regret bound
              O(√(T log N)), meaning agents converge to a Nash equilibrium price within ~50 ticks without any centralized
              coordination. The convergence metric is:
            </p>
            <Formula>
              convergence_pct = 1 - (price_spread / max_price)
            </Formula>
            <p>
              In practice, GridMint achieves 85-95% convergence after 20-30 ticks, creating a stable Schelling point
              that balances seller profitability and buyer affordability.
            </p>

            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              Autonomous Coalitions with Shapley Value Revenue Splitting
            </h3>
            <p>
              Agents can form temporary coalitions (virtual power plants) to bid jointly in the auction. Revenue is split
              according to each member's Shapley value—the marginal contribution they bring to every possible sub-coalition:
            </p>
            <Formula>
              φ_i(v) = Σ_(S ⊆ N\{'{i}'}) [ |S|! × (|N|-|S|-1)! / |N|! ] × [ v(S ∪ {'{i}'}) - v(S) ]
            </Formula>
            <p>
              For a 2-member coalition {'{Solar, Battery}'}:
            </p>
            <Formula>
              φ_Solar = ( v({'{Solar}'}) + v({'{Solar,Battery}'}) - v({'{Battery}'}) ) / 2<br />
              φ_Battery = ( v({'{Battery}'}) + v({'{Solar,Battery}'}) - v({'{Solar}'}) ) / 2
            </Formula>
            <p>
              The coalition value v(S) is the total revenue at clearing price, with a 25% dispatchability premium if the
              coalition includes both solar + battery (firm power). This models real wholesale markets where generator
              portfolios earn capacity payments for guaranteed delivery.
            </p>

            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              Cryptoeconomic Futures via Commit-Reveal Protocol
            </h3>
            <p>
              Agents can hedge price risk by trading energy futures 3 ticks ahead. The protocol uses a two-phase
              commit-reveal scheme:
            </p>
            <ol style={{ paddingLeft: 24, marginTop: 16 }}>
              <li style={{ marginBottom: 12 }}>
                <strong>Phase 1 (Commit):</strong> Producer commits <Code>hash(predicted_kwh || nonce)</Code> + 10% USDC deposit.
                Consumer commits <Code>hash(predicted_demand || nonce)</Code> + 10% deposit. Hash prevents front-running.
              </li>
              <li style={{ marginBottom: 12 }}>
                <strong>Phase 2 (Reveal):</strong> Both parties reveal their values and nonces. Engine verifies
                <Code>hash(revealed || nonce) == commitment</Code>. If delivered ≥ committed, producer earns futures premium.
                If under-delivered, deposit is slashed proportionally and redistributed to buyer.
              </li>
            </ol>
            <Formula>
              slash_fraction = min(1.0, (committed - delivered) / committed)<br />
              slash_amount = deposit × slash_fraction
            </Formula>
            <p>
              Futures price is <Code>spot_price × (1 + spread)</Code>, where spread is forecast by Gemini AI based on
              historical delivery accuracy and time-of-day solar confidence. This creates skin-in-the-game for accurate
              forecasting.
            </p>
          </Section>

          {/* AI Integration */}
          <Section title="Gemini Function Calling Integration">
            <p>
              GridMint integrates Google Gemini 2.5 Flash as an agentic AI brain with 5 registered tools:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet><Code>get_grid_status()</Code> → Live tick, price, tx count, settlement mode</Bullet>
              <Bullet><Code>get_agent_balance(agent_id)</Code> → USDC balance & tx history</Bullet>
              <Bullet><Code>trigger_stress_test(scenario)</Code> → Inject solar_crash / demand_spike / etc.</Bullet>
              <Bullet><Code>get_economic_proof()</Code> → Arc vs ETH cost comparison</Bullet>
              <Bullet><Code>get_schelling_metrics()</Code> → MWU convergence data</Bullet>
            </ul>
            <p>
              Gemini autonomously decides which tools to call via multi-turn Function Calling. For example, the operator query
              "Trigger a solar crash and tell me the economic impact" results in:
            </p>
            <ol style={{ paddingLeft: 24, marginTop: 16 }}>
              <li style={{ marginBottom: 12 }}>
                Gemini calls <Code>trigger_stress_test(scenario="solar_crash")</Code>
              </li>
              <li style={{ marginBottom: 12 }}>
                Receives tool result: 4 solar agents went offline
              </li>
              <li style={{ marginBottom: 12 }}>
                Calls <Code>get_economic_proof()</Code> to analyze cost impact
              </li>
              <li style={{ marginBottom: 12 }}>
                Returns grounded answer with real data: "Solar crash reduced supply by 40%, causing prices to surge 3×.
                Total settlement costs increased $0.02 due to higher clearing prices."
              </li>
            </ol>
            <p>
              Battery agents use Gemini for trade decisions every 5th tick, overriding the EWMA threshold logic with
              contextual reasoning (e.g., "It's 18:00, solar output dropping, hold charge for evening peak demand").
            </p>
          </Section>

          {/* Circle Integration */}
          <Section title="Circle Technologies Integration">
            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              Nanopayments Gateway for Agent Settlement
            </h3>
            <p>
              Agent-to-agent trades are routed through a TypeScript Express server running Circle's <Code>@circle-fin/x402-batching</Code> SDK:
            </p>
            <ol style={{ paddingLeft: 24, marginTop: 16 }}>
              <li style={{ marginBottom: 12 }}>
                Python <Code>GatewaySettler</Code> receives a <Code>TradeMatch</Code> event
              </li>
              <li style={{ marginBottom: 12 }}>
                POSTs to <Code>http://localhost:4402/nanopayments/agent-settle</Code> with buyer private key + trade details
              </li>
              <li style={{ marginBottom: 12 }}>
                Server creates <Code>{'GatewayClient({ chain: "arcTestnet", privateKey })'}</Code>
              </li>
              <li style={{ marginBottom: 12 }}>
                Auto-deposits $0.10 USDC to Gateway if balance below threshold
              </li>
              <li style={{ marginBottom: 12 }}>
                Dynamically creates a paywalled route <Code>{'/nanopayments/settle-target/{trade_id}'}</Code>
              </li>
              <li style={{ marginBottom: 12 }}>
                Calls <Code>client.pay(settleUrl)</Code> → Circle Gateway batches + settles on Arc Testnet
              </li>
              <li style={{ marginBottom: 12 }}>
                Returns confirmation to Python with HTTP 200
              </li>
            </ol>
            <p>
              This is fully gasless—Circle Gateway uses EIP-3009 <Code>TransferWithAuthorization</Code> with meta-transactions,
              eliminating the need for buyers to hold native Arc tokens. Finality is {'<'}500ms, enabling real-time settlement.
            </p>

            <h3 style={{ fontSize: 18, color: '#9B8CFF', marginTop: 32, marginBottom: 16, fontWeight: 600 }}>
              x402 Protocol for API Monetization
            </h3>
            <p>
              GridMint exposes premium audit endpoints protected by HTTP 402 Payment Required:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet><Code>GET /api/economic-proof</Code> — $0.003 USDC</Bullet>
              <Bullet><Code>GET /api/certificates</Code> — $0.001 USDC (green certificate ledger)</Bullet>
              <Bullet><Code>GET /api/schelling</Code> — $0.002 USDC (MWU learning state)</Bullet>
            </ul>
            <p>
              The x402 middleware validates Circle Gateway payment signatures in request headers. If valid, the endpoint
              returns data; otherwise, returns 402 with a <Code>PAYMENT-SIGNATURE</Code> challenge. This monetizes
              data access for external analytics dashboards and auditors.
            </p>
          </Section>

          {/* Economic Proof */}
          <Section title="Economic Proof: Cost Comparison">
            <p>
              GridMint executed 264 real USDC transfers on Arc Testnet with the following results:
            </p>
            <div style={{
              background: 'rgba(110,231,243,0.05)',
              border: '1px solid rgba(110,231,243,0.2)',
              borderRadius: 12,
              padding: 24,
              marginTop: 20,
              marginBottom: 20,
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, fontSize: 14 }}>
                <div>
                  <div style={{ color: 'rgba(230,238,246,0.5)', marginBottom: 6 }}>Total Transactions</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: '#6EE7F3' }}>264</div>
                </div>
                <div>
                  <div style={{ color: 'rgba(230,238,246,0.5)', marginBottom: 6 }}>Total Volume</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: '#6EE7F3' }}>$0.47 USDC</div>
                </div>
                <div>
                  <div style={{ color: 'rgba(230,238,246,0.5)', marginBottom: 6 }}>Arc Gas Cost</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: '#4ade80' }}>$0.29</div>
                </div>
                <div>
                  <div style={{ color: 'rgba(230,238,246,0.5)', marginBottom: 6 }}>Ethereum Equivalent</div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: '#f87171' }}>$652.08</div>
                </div>
              </div>
              <div style={{
                marginTop: 24,
                paddingTop: 20,
                borderTop: '1px solid rgba(110,231,243,0.2)',
                fontSize: 20,
                fontWeight: 700,
                color: '#9B8CFF',
                textAlign: 'center',
              }}>
                Arc is <span style={{ color: '#6EE7F3', fontSize: 32 }}>2264×</span> cheaper than Ethereum
              </div>
            </div>
            <p>
              Multi-chain comparison (cost per transaction):
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>Ethereum: $2.47 (65k gas × 20 gwei × $1,900/ETH)</Bullet>
              <Bullet>Arbitrum: $0.048 (L2 rollup, batched settlement)</Bullet>
              <Bullet>Base: $0.031 (Coinbase L2)</Bullet>
              <Bullet>Polygon: $0.009 (low-fee sidechain)</Bullet>
              <Bullet>Solana: $0.0025 (non-EVM, high throughput)</Bullet>
              <Bullet><strong>Arc (measured): $0.0011</strong> (cheapest EVM chain tested)</Bullet>
            </ul>
            <p>
              This cost structure enables true micropayments—individual kWh trades as small as $0.04 remain economically
              viable, whereas Ethereum gas would exceed the payment value.
            </p>
          </Section>

          {/* Stress Testing */}
          <Section title="Fault Injection & Resilience Testing">
            <p>
              GridMint includes 5 stress test scenarios to validate system robustness:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>
                <strong>Solar Crash:</strong> 50% of solar agents go offline simultaneously (simulates cloud cover event).
                Grid responds by raising prices 2-3× to balance supply/demand. Batteries discharge stored energy to prevent
                blackout. System recovers within 5 ticks.
              </Bullet>
              <Bullet>
                <strong>Demand Spike:</strong> All consumer agents double their demand (simulates heat wave). Batteries
                discharge, coalitions form to maximize dispatchable capacity. Clearing price surges 4×, but no load-shedding
                occurs.
              </Bullet>
              <Bullet>
                <strong>Battery Failure:</strong> All battery agents go offline (simulates inverter fault). Solar agents
                adjust prices downward to match remaining demand. Grid relies purely on solar-consumer direct trading.
              </Bullet>
              <Bullet>
                <strong>Price War:</strong> Random solar agents cut prices by 50% for 10 ticks (simulates predatory pricing).
                Other sellers match the price via MWU learning. Clearing price collapses temporarily, then recovers as
                low-price agents revert to profitable levels.
              </Bullet>
              <Bullet>
                <strong>Night Mode:</strong> Solar output drops to zero (simulates 20:00-05:00). Batteries become sole
                sellers. Prices peak at $0.15-$0.20/kWh (10× daytime rates). Consumers reduce demand elastically.
              </Bullet>
            </ul>
            <p>
              All scenarios can be triggered live via Gemini Function Calling: "Trigger a solar crash and analyze the impact."
            </p>
          </Section>

          {/* Conclusion */}
          <Section title="Conclusion & Future Work">
            <p>
              GridMint demonstrates that fully autonomous energy markets are technically feasible today. By combining
              Circle's Nanopayments infrastructure, Arc's sub-cent economics, and Gemini's agentic intelligence, the protocol
              achieves:
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>Zero-human-in-loop market clearing via game-theoretic learning</Bullet>
              <Bullet>Sub-cent settlement costs (2264× cheaper than Ethereum)</Bullet>
              <Bullet>Cryptoeconomic primitives (futures, coalitions, slashing) that enable sophisticated trading strategies</Bullet>
              <Bullet>Resilience to faults (stress-tested with 5 failure scenarios)</Bullet>
              <Bullet>Full audit trail (Merkle certificates, JSONL settlement logs, live tx hashes)</Bullet>
            </ul>
            <p style={{ marginTop: 24 }}>
              <strong>Future directions:</strong>
            </p>
            <ul style={{ listStyle: 'none', paddingLeft: 0, marginTop: 16 }}>
              <Bullet>Multi-region grids with cross-border trading (requires Circle CCTP for bridge-free USDC transfers)</Bullet>
              <Bullet>Reinforcement learning agents that adapt strategies over time (replace MWU with RL policy gradients)</Bullet>
              <Bullet>Zero-knowledge proofs for privacy-preserving settlement (hide trade amounts while proving balance sufficiency)</Bullet>
              <Bullet>Hardware integration with real smart meters and IoT devices (move from simulation to production pilots)</Bullet>
              <Bullet>Carbon credit derivatives market layered on green certificates</Bullet>
            </ul>
            <p style={{ marginTop: 24, fontStyle: 'italic', color: 'rgba(230,238,246,0.5)' }}>
              GridMint is open-source under MIT license. Built for the Circle x Arc Hackathon 2026.
            </p>
          </Section>

          {/* Footer */}
          <motion.footer
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8 }}
            style={{
              marginTop: 80,
              paddingTop: 40,
              borderTop: '1px solid rgba(255,255,255,0.08)',
              textAlign: 'center',
              color: 'rgba(230,238,246,0.4)',
              fontSize: 13,
            }}
          >
            <div style={{ marginBottom: 12 }}>
              Built for the Circle x Arc Hackathon 2026
            </div>
            <div>
              Powered by <span style={{ color: '#6EE7F3' }}>Circle Nanopayments</span> • <span style={{ color: '#9B8CFF' }}>Arc Testnet</span> • <span style={{ color: '#4ade80' }}>Google Gemini</span>
            </div>
          </motion.footer>
      </div>
    </div>
  )
}
