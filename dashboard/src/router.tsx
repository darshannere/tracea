import { createHashRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { SessionsPage } from '@/pages/SessionsPage'
import { EventTimelinePage } from '@/pages/EventTimelinePage'
import { IssuesPage } from '@/pages/IssuesPage'
import { SettingsPage } from '@/pages/SettingsPage'

export const router = createHashRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <SessionsPage /> },
      { path: 'sessions', element: <SessionsPage /> },
      { path: 'sessions/:id', element: <EventTimelinePage /> },
      { path: 'issues', element: <IssuesPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
])
