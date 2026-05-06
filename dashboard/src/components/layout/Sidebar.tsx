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
  Brain,
} from 'lucide-react'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/live', icon: Radio, label: 'Live' },
  { to: '/sessions', icon: Activity, label: 'Sessions' },
  { to: '/agents', icon: Bot, label: 'Agents' },
  { to: '/issues', icon: AlertCircle, label: 'Issues' },
  { to: '/brain', icon: Brain, label: 'Brain' },
  { to: '/team', icon: Users, label: 'Team' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  const { selectedUser, setSelectedUser, users } = useUser()

  return (
    <aside className="w-48 flex flex-col h-full border-r border-border bg-sidebar-bg">
      {/* Logo */}
      <div className="px-4 py-4 border-b border-sidebar-border">
        <h1 className="text-base font-bold text-sidebar-foreground">tracea</h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 px-4 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'text-white bg-sidebar-active-bg border-r-2 border-sidebar-active'
                  : 'text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-hover'
              )
            }
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User picker */}
      <div className="px-4 py-3 border-t border-sidebar-border">
        <label className="flex items-center gap-2 text-[11px] font-medium text-sidebar-foreground/40 mb-1.5 uppercase tracking-wider">
          <Users className="h-3 w-3" />
          Team member
        </label>
        <select
          value={selectedUser}
          onChange={(e) => setSelectedUser(e.target.value)}
          className="w-full text-sm bg-sidebar-bg border border-sidebar-border rounded px-2 py-1.5 text-sidebar-foreground focus:outline-none focus:ring-1 focus:ring-accent"
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