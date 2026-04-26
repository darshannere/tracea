import { useState } from 'react'
import { useUser } from '@/hooks/UserContext'
import api from '@/lib/api'
import { Users, Plus, Trash2, X } from 'lucide-react'
import { cn } from '@/lib/utils'

export function TeamPage() {
  const { users, refreshUsers } = useUser()
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ user_id: '', name: '', email: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.user_id.trim()) {
      setError('User ID is required')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      await api.post('/api/v1/users', {
        user_id: form.user_id.trim(),
        name: form.name.trim(),
        email: form.email.trim(),
      })
      setForm({ user_id: '', name: '', email: '' })
      setShowModal(false)
      refreshUsers()
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add user')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (user_id: string) => {
    if (!confirm(`Remove user "${user_id}"?`)) return
    try {
      await api.delete(`/api/v1/users/${encodeURIComponent(user_id)}`)
      refreshUsers()
    } catch {
      // silent
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-5 w-5 text-accent" />
          <h2 className="text-xl font-semibold">Team</h2>
          <span className="text-sm text-zinc-500">{users.length} members</span>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-accent text-white rounded-md hover:bg-accent/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add Member
        </button>
      </div>

      {/* Users table */}
      {users.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-zinc-500 border border-dashed border-zinc-300 rounded-lg">
          <Users className="h-8 w-8 mb-2" />
          <p className="text-sm font-medium">No team members yet</p>
          <p className="text-xs text-zinc-400">Add members to filter sessions by user</p>
        </div>
      ) : (
        <div className="border border-zinc-200 rounded-lg overflow-hidden bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-zinc-50 text-zinc-500 text-xs uppercase tracking-wide">
                <th className="text-left px-4 py-2.5 font-medium">User ID</th>
                <th className="text-left px-4 py-2.5 font-medium">Name</th>
                <th className="text-left px-4 py-2.5 font-medium">Email</th>
                <th className="text-left px-4 py-2.5 font-medium">Added</th>
                <th className="px-4 py-2.5 w-12"></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.user_id} className="border-t border-zinc-100 hover:bg-zinc-50">
                  <td className="px-4 py-3 font-mono text-xs text-zinc-700">{u.user_id}</td>
                  <td className="px-4 py-3 text-zinc-700">{u.name || '—'}</td>
                  <td className="px-4 py-3 text-zinc-500">{u.email || '—'}</td>
                  <td className="px-4 py-3 text-zinc-400 text-xs">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleDelete(u.user_id)}
                      className="text-zinc-400 hover:text-red-500 transition-colors"
                      title="Remove"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add member modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Add Team Member</h3>
              <button onClick={() => setShowModal(false)} className="text-zinc-400 hover:text-zinc-600">
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">User ID</label>
                <input
                  type="text"
                  value={form.user_id}
                  onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                  className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  placeholder="e.g. alice"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  placeholder="e.g. Alice Smith"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-500 mb-1">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full text-sm border border-zinc-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-accent"
                  placeholder="alice@example.com"
                />
              </div>
              {error && <p className="text-xs text-red-500">{error}</p>}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-100 rounded-md transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className={cn(
                    'px-3 py-1.5 text-sm font-medium bg-accent text-white rounded-md transition-colors',
                    submitting ? 'opacity-60' : 'hover:bg-accent/90'
                  )}
                >
                  {submitting ? 'Adding...' : 'Add Member'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
