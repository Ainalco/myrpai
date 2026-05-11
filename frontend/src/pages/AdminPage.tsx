import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Users,
  Workflow,
  Zap,
  DollarSign,
  ArrowUpDown,
  ChevronDown,
  ChevronUp,
  Building2,
} from 'lucide-react'
import { adminApi, AdminUserStats } from '@/lib/api'
import { formatCost } from '@/lib/cost'
import { AcornIcon } from '@/components/ui/acorn-icon'

type SortField = 'email' | 'workflow_count' | 'execution_count' | 'total_tokens' | 'cost' | 'acorns_spent' | 'acorn_balance' | 'last_active' | 'org_name' | 'current_crm' | 'meeting_tool'
type SortDir = 'asc' | 'desc'

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function getUserCost(user: AdminUserStats): number {
  return user.cost
}

interface OrgGroup {
  org_id: number | null
  org_name: string | null
  users: AdminUserStats[]
}

export default function AdminPage() {
  const navigate = useNavigate()
  const [sortField, setSortField] = useState<SortField>('total_tokens')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [collapsedOrgs, setCollapsedOrgs] = useState<Set<string>>(new Set())

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['admin', 'overview'],
    queryFn: () => adminApi.getOverview().then((r) => r.data),
  })

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const toggleOrgCollapse = (orgKey: string) => {
    setCollapsedOrgs((prev) => {
      const next = new Set(prev)
      if (next.has(orgKey)) {
        next.delete(orgKey)
      } else {
        next.add(orgKey)
      }
      return next
    })
  }

  const sortedUsers = React.useMemo(() => {
    if (!overview?.users) return []
    return [...overview.users].sort((a, b) => {
      let aVal: any
      let bVal: any
      if (sortField === 'cost') {
        aVal = getUserCost(a)
        bVal = getUserCost(b)
      } else if (sortField === 'current_crm' || sortField === 'meeting_tool') {
        aVal = (a as any).onboarding?.[sortField]
        bVal = (b as any).onboarding?.[sortField]
      } else {
        aVal = (a as any)[sortField]
        bVal = (b as any)[sortField]
      }
      if (sortField === 'last_active') {
        aVal = aVal ? new Date(aVal).getTime() : 0
        bVal = bVal ? new Date(bVal).getTime() : 0
      }
      if (typeof aVal === 'string') aVal = aVal.toLowerCase()
      if (typeof bVal === 'string') bVal = bVal.toLowerCase()
      if (aVal == null) aVal = ''
      if (bVal == null) bVal = ''
      if (aVal < bVal) return sortDir === 'asc' ? -1 : 1
      if (aVal > bVal) return sortDir === 'asc' ? 1 : -1
      return 0
    })
  }, [overview?.users, sortField, sortDir])

  // Group users by org
  const orgGroups = React.useMemo((): OrgGroup[] => {
    const map = new Map<string, OrgGroup>()
    for (const user of sortedUsers) {
      const key = user.org_id != null ? String(user.org_id) : '__none__'
      if (!map.has(key)) {
        map.set(key, {
          org_id: user.org_id ?? null,
          org_name: user.org_name ?? null,
          users: [],
        })
      }
      map.get(key)!.users.push(user)
    }
    // Sort groups: named orgs first (alphabetically), then no-org
    return Array.from(map.values()).sort((a, b) => {
      if (a.org_name == null && b.org_name != null) return 1
      if (a.org_name != null && b.org_name == null) return -1
      if (a.org_name == null && b.org_name == null) return 0
      return a.org_name!.toLowerCase().localeCompare(b.org_name!.toLowerCase())
    })
  }, [sortedUsers])

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />
    return sortDir === 'asc' ? (
      <ChevronUp className="h-3 w-3 ml-1" />
    ) : (
      <ChevronDown className="h-3 w-3 ml-1" />
    )
  }

  const totalCost = overview?.total_cost ?? 0
  const totalActualCost = overview?.total_actual_cost ?? 0

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header with Light Gradient */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />

        <div className="flex items-center justify-between relative z-10">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">
              Admin Portal
            </h1>
            <p className="text-sm sm:text-base text-scurry-latte mt-2">
              Platform-wide statistics and user analytics
            </p>
          </div>
        </div>
      </div>

      <div className="border-b border-scurry-gray-border">
        <nav className="flex gap-4">
          <Link
            to="/admin"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-scurry-orange text-scurry-orange"
          >
            Overview
          </Link>
          <Link
            to="/admin/usage"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
          >
            Usage &amp; Cost
          </Link>
          <Link
            to="/admin/models"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
          >
            Models
          </Link>
          <Link
            to="/admin/rag"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
          >
            RAG
          </Link>
        </nav>
      </div>

      {overviewLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
        </div>
      ) : overview ? (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            {[
              { label: 'Total Users', value: overview.total_users as React.ReactNode, sub: null as string | null, icon: Users, color: 'text-blue-600 bg-blue-50' },
              { label: 'Total Workflows', value: overview.total_workflows, sub: null, icon: Workflow, color: 'text-purple-600 bg-purple-50' },
              { label: 'Total Executions', value: overview.total_executions, sub: null, icon: Zap, color: 'text-green-600 bg-green-50' },
              {
                label: 'API Cost',
                value: formatCost(totalCost),
                sub: totalActualCost > 0 ? `Anthropic: ${formatCost(totalActualCost)}` : null,
                icon: DollarSign,
                color: 'text-orange-600 bg-scurry-orange-light',
              },
              { label: 'Acorns Spent', value: <><AcornIcon className="w-5 h-5" /> {Math.round(overview.total_acorns_spent || 0).toLocaleString()}</>, sub: null, icon: DollarSign, color: 'text-amber-700 bg-amber-50' },
            ].map((card) => {
              const Icon = card.icon
              return (
                <div key={card.label} className="bg-white rounded-lg border border-scurry-gray-border p-4">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${card.color}`}>
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-xs text-scurry-latte">{card.label}</p>
                      <p className="text-xl font-bold text-scurry-espresso">{card.value}</p>
                      {card.sub && (
                        <p className="text-[10px] text-scurry-gray-muted mt-0.5">{card.sub}</p>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="bg-white rounded-lg border border-scurry-gray-border overflow-hidden">
            <div className="px-4 py-3 border-b border-scurry-gray-border">
              <h2 className="text-sm font-semibold text-scurry-espresso">User Breakdown</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-scurry-foam text-left text-xs text-scurry-latte uppercase tracking-wider">
                    {[
                      { field: 'org_name' as SortField, label: 'Organization' },
                      { field: 'email' as SortField, label: 'User' },
                      { field: 'current_crm' as SortField, label: 'CRM' },
                      { field: 'meeting_tool' as SortField, label: 'Meeting Tool' },
                      { field: 'workflow_count' as SortField, label: 'Workflows' },
                      { field: 'execution_count' as SortField, label: 'Executions' },
                      { field: 'total_tokens' as SortField, label: 'Tokens' },
                      { field: 'cost' as SortField, label: 'API Cost' },
                      { field: 'acorns_spent' as SortField, label: 'Acorns Spent' },
                      { field: 'acorn_balance' as SortField, label: 'Balance' },
                      { field: 'last_active' as SortField, label: 'Last Active' },
                    ].map((col) => (
                      <th
                        key={col.field}
                        className="px-4 py-3 cursor-pointer hover:bg-scurry-gray-light select-none"
                        onClick={() => toggleSort(col.field)}
                      >
                        <span className="flex items-center">
                          {col.label}
                          <SortIcon field={col.field} />
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-scurry-gray-border">
                  {orgGroups.map((group) => {
                    const orgKey = group.org_id != null ? String(group.org_id) : '__none__'
                    const isCollapsed = collapsedOrgs.has(orgKey)
                    const hasOrg = group.org_id != null

                    return (
                      <React.Fragment key={orgKey}>
                        {/* Org header row */}
                        <tr
                          className="bg-scurry-foam/70 border-t-2 border-scurry-gray-border cursor-pointer select-none"
                          onClick={() => toggleOrgCollapse(orgKey)}
                        >
                          <td className="px-4 py-2" colSpan={11}>
                            <div className="flex items-center gap-2">
                              {isCollapsed ? (
                                <ChevronDown className="h-3.5 w-3.5 text-scurry-latte" />
                              ) : (
                                <ChevronUp className="h-3.5 w-3.5 text-scurry-latte" />
                              )}
                              <Building2 className="h-3.5 w-3.5 text-scurry-latte" />
                              {hasOrg ? (
                                <button
                                  className="text-xs font-semibold text-scurry-orange hover:underline"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    navigate(`/admin/org/${group.org_id}`)
                                  }}
                                >
                                  {group.org_name}
                                </button>
                              ) : (
                                <span className="text-xs font-semibold text-scurry-latte">No Organization</span>
                              )}
                              <span className="text-xs text-scurry-gray-muted ml-1">
                                ({group.users.length} {group.users.length === 1 ? 'user' : 'users'})
                              </span>
                            </div>
                          </td>
                        </tr>

                        {/* User rows */}
                        {!isCollapsed && group.users.map((user) => (
                          <tr
                            key={user.id}
                            className="hover:bg-scurry-foam/50 cursor-pointer"
                            onClick={() => navigate(`/admin/user/${user.id}`)}
                          >
                            <td className="px-4 py-3 text-xs text-scurry-latte">
                              {user.org_name ?? <span className="text-scurry-gray-muted">—</span>}
                            </td>
                            <td className="px-4 py-3">
                              <div>
                                <span className="font-medium text-scurry-espresso">{user.full_name || user.email}</span>
                                {user.is_superadmin && (
                                  <span className="ml-2 text-[10px] bg-scurry-orange text-white px-1.5 py-0.5 rounded-full font-medium">
                                    Admin
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-scurry-gray-muted">{user.email}</span>
                            </td>
                            <td className="px-4 py-3 text-scurry-espresso">
                              {(user as any).onboarding?.current_crm || <span className="text-scurry-gray-muted">—</span>}
                            </td>

                            <td className="px-4 py-3 text-scurry-espresso">
                              {(user as any).onboarding?.meeting_tool || <span className="text-scurry-gray-muted">—</span>}
                            </td>
                            <td className="px-4 py-3 text-scurry-espresso">{user.workflow_count}</td>
                            <td className="px-4 py-3 text-scurry-espresso">{user.execution_count}</td>
                            <td className="px-4 py-3">
                              <span className="font-medium text-scurry-espresso">{formatTokens(user.total_tokens)}</span>
                              <div className="text-[10px] text-scurry-gray-muted">
                                {formatTokens(user.total_prompt_tokens)} in / {formatTokens(user.total_completion_tokens)} out
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <span className="font-medium text-scurry-espresso">
                                {formatCost(getUserCost(user))}
                              </span>
                              {user.actual_cost != null && user.actual_cost !== getUserCost(user) && (
                                <div className="text-[10px] text-scurry-gray-muted">
                                  actual {formatCost(user.actual_cost)}
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <span className="font-medium text-amber-700">
                                <AcornIcon className="w-3.5 h-3.5" /> {Math.round(user.acorns_spent || 0).toLocaleString()}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1.5">
                                <span className="font-medium text-scurry-espresso">
                                  {Math.round(user.acorn_balance || 0).toLocaleString()}
                                </span>
                                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${user.plan === 'redwood' ? 'text-green-700 bg-green-50' :
                                  user.plan === 'oak' ? 'text-scurry-orange bg-scurry-orange-light' :
                                    user.plan === 'seedling' ? 'text-gray-600 bg-gray-100' :
                                      'text-scurry-latte bg-gray-50'
                                  }`}>
                                  {user.plan || '—'}
                                </span>
                              </div>
                            </td>
                            <td className="px-4 py-3 text-scurry-latte">{formatDate(user.last_active)}</td>
                          </tr>
                        ))}
                      </React.Fragment>
                    )
                  })}
                  {sortedUsers.length === 0 && (
                    <tr>
                      <td colSpan={11} className="px-4 py-8 text-center text-scurry-gray-muted">
                        No users found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
