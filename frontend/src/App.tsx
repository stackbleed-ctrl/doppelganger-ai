import { Routes, Route } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import { useHealthPoller } from './hooks/useHealthPoller'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { ChatPage } from './pages/ChatPage'
import { MemoryPage } from './pages/MemoryPage'
import { SimPage } from './pages/SimPage'
import { SkillsPage } from './pages/SkillsPage'
import { PerceptionPage } from './pages/PerceptionPage'
import { PersonasPage } from './pages/PersonasPage'
import { useStore } from './lib/store'
import clsx from 'clsx'

export default function App() {
  const { send } = useWebSocket()
  useHealthPoller()
  const { sidebarOpen } = useStore()

  return (
    <div className="relative flex h-screen w-screen overflow-hidden bg-void scanlines">
      <div className="pointer-events-none absolute inset-0 z-0">
        <div className="absolute -left-32 top-1/4 h-96 w-96 rounded-full bg-cyan/5 blur-3xl" />
        <div className="absolute -right-32 bottom-1/4 h-96 w-96 rounded-full bg-purple/5 blur-3xl" />
      </div>
      <Sidebar />
      <div className={clsx(
        'relative z-10 flex flex-1 flex-col overflow-hidden transition-all duration-300',
        sidebarOpen ? 'ml-64' : 'ml-0'
      )}>
        <TopBar wsSend={send} />
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/"           element={<ChatPage wsSend={send} />} />
            <Route path="/chat"       element={<ChatPage wsSend={send} />} />
            <Route path="/memory"     element={<MemoryPage />} />
            <Route path="/sim"        element={<SimPage />} />
            <Route path="/skills"     element={<SkillsPage />} />
            <Route path="/perception" element={<PerceptionPage />} />
            <Route path="/personas"   element={<PersonasPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
