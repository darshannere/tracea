import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import api from '@/lib/api'

export interface TeamUser {
  user_id: string
  name: string
  email: string
  created_at: string
}

interface UserContextValue {
  selectedUser: string
  setSelectedUser: (user: string) => void
  users: TeamUser[]
  refreshUsers: () => void
}

const UserContext = createContext<UserContextValue>({
  selectedUser: '',
  setSelectedUser: () => {},
  users: [],
  refreshUsers: () => {},
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [selectedUser, setSelectedUser] = useState(() => {
    return localStorage.getItem('tracea_selected_user') || ''
  })
  const [users, setUsers] = useState<TeamUser[]>([])

  const refreshUsers = () => {
    api.get<{ users: TeamUser[] }>('/api/v1/users')
      .then((res) => setUsers(res.data.users))
      .catch(() => {})
  }

  useEffect(() => {
    refreshUsers()
  }, [])

  useEffect(() => {
    if (selectedUser) {
      localStorage.setItem('tracea_selected_user', selectedUser)
    } else {
      localStorage.removeItem('tracea_selected_user')
    }
  }, [selectedUser])

  return (
    <UserContext.Provider value={{ selectedUser, setSelectedUser, users, refreshUsers }}>
      {children}
    </UserContext.Provider>
  )
}

export function useUser() {
  return useContext(UserContext)
}
