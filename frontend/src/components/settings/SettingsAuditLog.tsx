import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { teamApi } from '@/lib/api'
import { Loader2 } from 'lucide-react'

const actionBadgeStyles: Record<string, string> = {
  billing: 'text-scurry-orange bg-scurry-orange-light',
  integration: 'text-gray-600 bg-gray-100',
  team: 'text-scurry-orange bg-scurry-orange-light',
  login: 'text-green-700 bg-green-50',
  workflow: 'text-gray-600 bg-gray-100',
  settings: 'text-gray-600 bg-gray-100',
}

const FILTERS = ['all', 'login', 'billing', 'team', 'integration', 'workflow', 'settings']

const SettingsAuditLog: React.FC = () => {
  const { user } = useAuth()
  const role = user?.role || 'member'
  const isMember = role === 'member'
  const [filter, setFilter] = useState('all')

  const { data: auditData, isLoading } = useQuery({
    queryKey: ['audit-log', filter],
    queryFn: () =>
      teamApi
        .getAuditLog({
          action: filter === 'all' ? undefined : filter,
          limit: 50,
        })
        .then((r) => r.data),
  })

  const logs = Array.isArray(auditData) ? auditData : auditData?.entries ?? []

  return (
    <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900">
            <span className="text-scurry-orange">📋</span> {isMember ? 'Your Activity Log' : 'Audit Log'}
          </div>
          <p className="text-sm text-gray-500">
            {isMember ? 'Your account activity and events.' : 'All significant account events.'}
          </p>
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg text-[11px] font-bold capitalize border transition-colors ${
                filter === f
                  ? 'bg-scurry-orange text-white border-scurry-orange'
                  : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-scurry-orange" />
        </div>
      ) : logs.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                {(isMember ? ['Timestamp', 'Type', 'Description'] : ['Timestamp', 'User', 'Type', 'Description']).map((h) => (
                  <th
                    key={h}
                    className="text-left px-2.5 py-2 text-[11px] font-bold text-gray-500 border-b border-gray-200 uppercase tracking-wide"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map((l: any, i: number) => (
                <tr key={l.id || i}>
                  <td className="px-2.5 py-3 border-b border-gray-200 font-mono text-[11px] text-gray-500 whitespace-nowrap">
                    {l.created_at
                      ? new Date(l.created_at).toLocaleString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : l.date || '—'}
                  </td>
                  {!isMember && (
                    <td className="px-2.5 py-3 border-b border-gray-200 font-medium">
                      {l.user_email || l.user_name || l.user || '—'}
                    </td>
                  )}
                  <td className="px-2.5 py-3 border-b border-gray-200">
                    <span
                      className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                        actionBadgeStyles[l.action] || 'text-gray-600 bg-gray-100'
                      }`}
                    >
                      {l.action || '—'}
                    </span>
                  </td>
                  <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500">
                    {l.description || l.desc || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-gray-500 text-center py-8">No audit events found.</p>
      )}
    </div>
  )
}

export default SettingsAuditLog
