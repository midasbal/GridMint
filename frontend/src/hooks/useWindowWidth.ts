import { useState, useEffect } from 'react'

/**
 * Returns the current window width and re-renders on resize.
 * Breakpoints: mobile < 768, tablet < 1100, desktop >= 1100
 */
export function useWindowWidth() {
  const [w, setW] = useState(typeof window !== 'undefined' ? window.innerWidth : 1280)
  useEffect(() => {
    const handler = () => setW(window.innerWidth)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return w
}
