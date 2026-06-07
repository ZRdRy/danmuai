import { useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { CommunityProvider } from './context/CommunityContext'
import { ThemeProvider } from './context/ThemeContext'
import { ToastProvider } from './context/ToastContext'
import { useMaintenanceGate } from './hooks/useMaintenanceGate'
import { HomePage } from './pages/HomePage'
import { MaintenancePage } from './pages/MaintenancePage'
import { PostDetailPage } from './pages/PostDetailPage'
import { ModerationPage } from './pages/ModerationPage'

function AppRoutes() {
  const [search, setSearch] = useState('')

  return (
    <Routes>
      <Route
        path="/"
        element={<HomePage search={search} onSearchChange={setSearch} />}
      />
      <Route
        path="/post/:id"
        element={
          <PostDetailPage search={search} onSearchChange={setSearch} />
        }
      />
      <Route
        path="/moderation"
        element={
          <ModerationPage search={search} onSearchChange={setSearch} />
        }
      />
    </Routes>
  )
}

function AppShell() {
  const { loading, inMaintenance, message } = useMaintenanceGate()

  if (loading) {
    return (
      <div
        className="flex min-h-screen items-center justify-center text-sm"
        style={{ color: 'var(--color-text-dim)' }}
      >
        加载中…
      </div>
    )
  }

  if (inMaintenance) {
    return <MaintenancePage message={message} />
  }

  return (
    <CommunityProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </CommunityProvider>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AppShell />
      </ToastProvider>
    </ThemeProvider>
  )
}
