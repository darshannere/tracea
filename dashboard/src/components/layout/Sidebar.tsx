import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Activity, AlertCircle, Settings } from 'lucide-react'

const navItems = [
  { to: '/sessions', icon: Activity, label: 'Sessions' },
  { to: '/issues', icon: AlertCircle, label: 'Issues' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  return (
    <aside className="w-60 bg-zinc-100 flex flex-col h-full">
      <div className="px-4 py-4 border-b border-zinc-200">
        <h1 className="text-lg font-bold text-zinc-900">tracea</h1>
      </div>
      <nav className="flex-1 py-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'text-accent bg-white/50 border-r-2 border-accent'
                  : 'text-zinc-600 hover:text-zinc-900 hover:bg-white/30'
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
