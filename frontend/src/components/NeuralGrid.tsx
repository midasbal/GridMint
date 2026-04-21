import React, { useEffect, useRef } from 'react'

interface Props {
  width?: number
  height?: number
}

export default function NeuralGrid({ width = 600, height = 480 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)

    type Node = {
      x: number; y: number; vx: number; vy: number
      r: number; type: 'solar' | 'battery' | 'consumer'
      pulse: number; pulseSpeed: number; energy: number
    }

    const COLORS = { solar: '#facc15', battery: '#6EE7F3', consumer: '#9B8CFF' }
    const TYPES: Array<'solar' | 'battery' | 'consumer'> = ['solar', 'battery', 'consumer']

    const nodes: Node[] = Array.from({ length: 14 }, (_, i) => ({
      x: 40 + Math.random() * (width - 80),
      y: 40 + Math.random() * (height - 80),
      vx: (Math.random() - 0.5) * 0.35,
      vy: (Math.random() - 0.5) * 0.35,
      r: 5 + Math.random() * 4,
      type: TYPES[i % 3],
      pulse: Math.random() * Math.PI * 2,
      pulseSpeed: 0.025 + Math.random() * 0.02,
      energy: Math.random(),
    }))

    type Packet = {
      from: number; to: number; t: number; speed: number; color: string
    }
    const packets: Packet[] = []
    let frame = 0

    const spawnPacket = () => {
      const from = Math.floor(Math.random() * nodes.length)
      let to = Math.floor(Math.random() * nodes.length)
      while (to === from) to = Math.floor(Math.random() * nodes.length)
      const fromNode = nodes[from]
      packets.push({
        from, to, t: 0, speed: 0.008 + Math.random() * 0.006,
        color: COLORS[fromNode.type],
      })
    }

    let raf: number
    const draw = () => {
      ctx.clearRect(0, 0, width, height)
      frame++

      // Spawn packets every ~40 frames
      if (frame % 40 === 0 && packets.length < 12) spawnPacket()

      // Draw connections
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const dist = Math.sqrt(dx * dx + dy * dy)
          if (dist < 180) {
            const alpha = (1 - dist / 180) * 0.18
            ctx.beginPath()
            ctx.moveTo(nodes[i].x, nodes[i].y)
            ctx.lineTo(nodes[j].x, nodes[j].y)
            ctx.strokeStyle = `rgba(110,231,243,${alpha})`
            ctx.lineWidth = 0.8
            ctx.stroke()
          }
        }
      }

      // Draw packets (energy balls flying between nodes)
      for (let i = packets.length - 1; i >= 0; i--) {
        const p = packets[i]
        p.t += p.speed
        if (p.t >= 1) { packets.splice(i, 1); continue }
        const fx = nodes[p.from].x, fy = nodes[p.from].y
        const tx = nodes[p.to].x, ty = nodes[p.to].y
        const px = fx + (tx - fx) * p.t
        const py = fy + (ty - fy) * p.t

        const grad = ctx.createRadialGradient(px, py, 0, px, py, 7)
        grad.addColorStop(0, p.color)
        grad.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(px, py, 7, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()

        ctx.beginPath()
        ctx.arc(px, py, 2.5, 0, Math.PI * 2)
        ctx.fillStyle = '#fff'
        ctx.fill()
      }

      // Draw nodes
      nodes.forEach(n => {
        n.pulse += n.pulseSpeed
        const glowR = n.r + 3 + Math.sin(n.pulse) * 3

        // Outer glow ring
        const ring = ctx.createRadialGradient(n.x, n.y, n.r * 0.5, n.x, n.y, glowR * 2.5)
        ring.addColorStop(0, COLORS[n.type] + '55')
        ring.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(n.x, n.y, glowR * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = ring
        ctx.fill()

        // Core
        ctx.beginPath()
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2)
        ctx.fillStyle = COLORS[n.type]
        ctx.shadowColor = COLORS[n.type]
        ctx.shadowBlur = 12
        ctx.fill()
        ctx.shadowBlur = 0

        // Inner highlight
        ctx.beginPath()
        ctx.arc(n.x - n.r * 0.25, n.y - n.r * 0.25, n.r * 0.35, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255,255,255,0.55)'
        ctx.fill()

        // Move
        n.x += n.vx; n.y += n.vy
        if (n.x < n.r || n.x > width - n.r) n.vx *= -1
        if (n.y < n.r || n.y > height - n.r) n.vy *= -1
      })

      raf = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(raf)
  }, [width, height])

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height, display: 'block', borderRadius: 20 }}
    />
  )
}
