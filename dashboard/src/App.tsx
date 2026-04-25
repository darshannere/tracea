import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { Toaster } from 'sonner'
import { UserProvider } from '@/hooks/UserContext'

export default function App() {
  return (
    <UserProvider>
      <RouterProvider router={router} />
      <Toaster position="bottom-right" richColors />
    </UserProvider>
  )
}
