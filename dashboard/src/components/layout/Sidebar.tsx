import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useUser } from '@/hooks/UserContext'
import {
  LayoutDashboard,
  Activity,
  Bot,
  AlertCircle,
  Settings,
  Radio,
  Users,
} from 'lucide-react'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/live', icon: Radio, label: 'Live' },
  { to: '/sessions', icon: Activity, label: 'Sessions' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/issues', icon: AlertCircle, label: 'Issues' },
  { to: '/team', icon: Users, label: 'Team' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  const { selectedUser, setSelectedUser, users } = useUser()

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

      {/* User picker */}
      <div className="px-4 py-3 border-t border-zinc-200">
        <label className="flex items-center gap-2 text-xs font-medium text-zinc-500 mb-1.5">
          <Users className="h-3.5 w-3.5" />
          Team member
        </label>
        <select
          value={selectedUser}
          onChange={(e) => setSelectedUser(e.target.value)}
          className="w-full text-sm bg-white border border-zinc-300 rounded-md px-2 py-1.5 text-zinc-700 focus:outline-none focus:ring-1 focus:ring-accent"
        >
          <option value="">All members</option>
          {users.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.name || u.user_id}
            </option>
          ))}
        </select>
      </div>
    </aside>
  )
}
