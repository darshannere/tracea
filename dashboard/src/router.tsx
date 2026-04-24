import { createHashRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { SessionsPage } from '@/pages/SessionsPage'
import { EventTimelinePage } from '@/pages/EventTimelinePage'
import { AgentsPage } from '@/pages/AgentsPage'
import { IssuesPage } from '@/pages/IssuesPage'
import { SettingsPage } from '@/pages/SettingsPage'

export const router = createHashRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'sessions', element: <SessionsPage /> },
      { path: 'sessions/:id', element: <EventTimelinePage /> },
      { path: 'agents', element: <AgentsPage /> },
      { path: 'issues', element: <IssuesPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
])
