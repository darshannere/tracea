import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { Toaster } from 'sonner'

export default function App() {
  return (
    <>
      <RouterProvider router={router} />
      <Toaster position="bottom-right" richColors />
    </>
  )
}
