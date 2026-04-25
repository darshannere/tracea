import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'

interface UserContextValue {
  selectedUser: string
  setSelectedUser: (user: string) => void
  users: string[]
  setUsers: (users: string[]) => void
}

const UserContext = createContext<UserContextValue>({
  selectedUser: '',
  setSelectedUser: () => {},
  users: [],
  setUsers: () => {},
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [selectedUser, setSelectedUser] = useState(() => {
    return localStorage.getItem('tracea_selected_user') || ''
  })
  const [users, setUsers] = useState<string[]>([])

  useEffect(() => {
    if (selectedUser) {
      localStorage.setItem('tracea_selected_user', selectedUser)
    } else {
      localStorage.removeItem('tracea_selected_user')
    }
  }, [selectedUser])

  return (
    <UserContext.Provider value={{ selectedUser, setSelectedUser, users, setUsers }}>
      {children}
    </UserContext.Provider>
  )
}

export function useUser() {
  return useContext(UserContext)
}
