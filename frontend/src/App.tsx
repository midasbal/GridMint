import React from 'react'
import { Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Whitepaper from './pages/Whitepaper'

export default function App(){
  return (
    <Routes>
      <Route path="/" element={<Landing/>} />
      <Route path="/dashboard" element={<Dashboard/>} />
      <Route path="/whitepaper" element={<Whitepaper/>} />
    </Routes>
  )
}
