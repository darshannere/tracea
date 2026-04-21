import { Outlet } from 'react-router-dom'
import { RcaBanner } from './RcaBanner'
import { Sidebar } from './Sidebar'
import { ConnectionErrorBanner } from './ConnectionErrorBanner'

export function AppShell() {
  return (
    <div className="flex flex-col h-screen">
      <ConnectionErrorBanner />
      <RcaBanner />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 bg-white overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
