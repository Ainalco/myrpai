import { useState, useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ChevronLeft, ChevronRight, DollarSign, Workflow, Zap, Calendar, RotateCcw } from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { adminApi } from '@/lib/api'
import { formatCost } from '@/lib/cost'
import { AcornIcon } from '@/components/ui/acorn-icon'

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

function formatDateTime(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }) + ', ' + d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
}
function displayValue(value?: string | null): string {
  if (!value || !value.trim()) return '—'
  return value
}
export default function AdminUserPage() {
  const { id } = useParams<{ id: string }>()
  const [preset, setPreset] = useState<number>(0) // 0=all, 7, 30, 90, -1=custom
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const queryParams = useMemo(() => {
    if (preset === -1 && startDate) {
      return { start_date: startDate, end_date: endDate || undefined }
    }
    if (preset > 0) return { days: preset }
    return {}
  }, [preset, startDate, endDate])

  const [activityPage, setActivityPage] = useState(0)
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const queryClient = useQueryClient()

  const resetMutation = useMutation({
    mutationFn: () => adminApi.resetUserUsage(Number(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin'] })
      setShowResetConfirm(false)
    },
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'user', id, queryParams],
    queryFn: () => adminApi.getUserDetail(Number(id), queryParams).then((r) => r.data),
    enabled: !!id,
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <Link to="/admin" className="inline-flex items-center gap-1 text-sm text-scurry-orange hover:underline">
          <ArrowLeft className="h-4 w-4" />
          Back to Admin
        </Link>
        <div className="bg-white rounded-lg border border-scurry-gray-border p-8 text-center text-scurry-gray-muted">
          User not found
        </div>
      </div>
    )
  }

  const { user, workflows, usage_by_source, recent_activity } = data
  const onboarding = (user as any).onboarding ?? {}

  const totalCost = data.total_cost
  const totalActualCost = data.total_actual_cost ?? 0
  const totalExecutions = workflows.reduce((sum, w) => sum + w.execution_count, 0)

  const PAGE_SIZE = 10
  const totalPages = Math.ceil(recent_activity.length / PAGE_SIZE)
  const pagedActivity = recent_activity.slice(activityPage * PAGE_SIZE, (activityPage + 1) * PAGE_SIZE)

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header with Light Gradient */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />

        <div className="relative z-10">
          <div className="flex items-start justify-between">
            <div>
              <Link to="/admin" className="inline-flex items-center gap-1 text-sm text-scurry-orange hover:underline mb-3">
                <ArrowLeft className="h-4 w-4" />
                Back to Admin
              </Link>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">
                  {user.full_name || user.email}
                </h1>
                {user.is_active && (
                  <span className="text-[10px] bg-scurry-orange text-white px-1.5 py-0.5 rounded-full font-medium">
                    Admin
                  </span>
                )}
                {user.plan && user.plan !== 'none' && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${user.plan === 'redwood' ? 'bg-green-100 text-green-700' :
                    user.plan === 'oak' ? 'bg-scurry-orange-light text-scurry-orange' :
                      user.plan === 'seedling' ? 'bg-gray-100 text-gray-600' :
                        user.plan === 'trialing' ? 'bg-amber-100 text-amber-700' :
                          'bg-gray-100 text-gray-600'
                    }`}>
                    {user.plan}
                  </span>
                )}
              </div>
            </div>
            <div className="relative">
              {showResetConfirm ? (
                <div className="flex items-center gap-2 bg-white rounded-lg border border-red-200 px-3 py-2 shadow-sm">
                  <span className="text-xs text-red-600 font-medium">Reset all usage?</span>
                  <button
                    onClick={() => resetMutation.mutate()}
                    disabled={resetMutation.isPending}
                    className="px-2 py-1 text-xs font-medium bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                  >
                    {resetMutation.isPending ? 'Resetting...' : 'Confirm'}
                  </button>
                  <button
                    onClick={() => setShowResetConfirm(false)}
                    className="px-2 py-1 text-xs font-medium text-scurry-latte hover:text-scurry-espresso"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowResetConfirm(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 bg-white border border-red-200 rounded-md hover:bg-red-50 transition-colors"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reset Usage
                </button>
              )}
            </div>
          </div>
          <p className="text-sm sm:text-base text-scurry-latte mt-2">{user.email}</p>
          {user.created_at && (
            <p className="text-xs text-scurry-latte mt-0.5">Joined {formatDate(user.created_at)}</p>
          )}
        </div>
      </div>

      {/* Date filter */}
      <div className="flex flex-wrap items-center gap-2">
        {[
          { label: 'All Time', value: 0 },
          { label: '7d', value: 7 },
          { label: '30d', value: 30 },
          { label: '90d', value: 90 },
          { label: 'Custom', value: -1 },
        ].map((opt) => (
          <button
            key={opt.value}
            onClick={() => { setPreset(opt.value); setActivityPage(0) }}
            className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${preset === opt.value
              ? 'bg-scurry-orange text-white border-scurry-orange'
              : 'bg-white text-scurry-latte border-scurry-gray-border hover:border-scurry-orange'
              }`}
          >
            {opt.value === -1 && <Calendar className="inline h-3.5 w-3.5 mr-1 -mt-0.5" />}
            {opt.label}
          </button>
        ))}
        {preset === -1 && (
          <div className="flex items-center gap-2 ml-1">
            <input
              type="date"
              value={startDate}
              onChange={(e) => { setStartDate(e.target.value); setActivityPage(0) }}
              className="px-2 py-1.5 text-sm rounded-md border border-scurry-gray-border bg-white text-scurry-espresso focus:outline-none focus:border-scurry-orange"
            />
            <span className="text-xs text-scurry-latte">to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); setActivityPage(0) }}
              className="px-2 py-1.5 text-sm rounded-md border border-scurry-gray-border bg-white text-scurry-espresso focus:outline-none focus:border-scurry-orange"
            />
          </div>
        )}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {[
          {
            label: 'API Cost',
            value: formatCost(totalCost) as React.ReactNode,
            sub: (totalActualCost > 0 && totalActualCost !== totalCost ? `Anthropic: ${formatCost(totalActualCost)}` : null) as string | null,
            icon: DollarSign,
            color: 'text-orange-600 bg-orange-50',
          },
          { label: 'Acorns Spent', value: <><AcornIcon className="w-5 h-5" /> {Math.round(data.total_acorns_spent || 0).toLocaleString()}</>, sub: null, icon: DollarSign, color: 'text-amber-700 bg-amber-50' },
          { label: 'Acorn Balance', value: Math.round(user.acorn_balance || 0).toLocaleString(), sub: null, icon: DollarSign, color: 'text-green-600 bg-green-50' },
          { label: 'Workflows', value: workflows.length, sub: null, icon: Workflow, color: 'text-purple-600 bg-purple-50' },
          { label: 'Executions', value: totalExecutions, sub: null, icon: Zap, color: 'text-green-600 bg-green-50' },
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
      {/* Signup Info */}
      <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
        <h2 className="text-sm font-semibold text-scurry-espresso mb-4">Signup Info</h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { label: 'Company', value: onboarding.company_name },
            { label: 'Team Size', value: onboarding.team_size },
            { label: 'Current CRM', value: onboarding.current_crm },
            { label: 'Meeting Tool', value: onboarding.meeting_tool },
            { label: 'Meetings / Week', value: onboarding.meetings_per_week },
            { label: 'Deal Cycle', value: onboarding.deal_cycle },
          ].map((item) => (
            <div
              key={item.label}
              className="rounded-lg border border-scurry-gray-border bg-scurry-foam/40 p-3"
            >
              <p className="text-xs text-scurry-latte">{item.label}</p>
              <p className="mt-1 text-sm font-medium text-scurry-espresso">
                {displayValue(item.value)}
              </p>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-lg border border-scurry-gray-border bg-scurry-foam/40 p-3">
          <p className="text-xs text-scurry-latte">Challenge</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-scurry-espresso">
            {displayValue(onboarding.challenge)}
          </p>
        </div>
      </div>
      {/* Token Usage by Source */}
      <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
        <h2 className="text-sm font-semibold text-scurry-espresso mb-4">Usage by Source</h2>
        {usage_by_source.length > 0 ? (
          <ResponsiveContainer width="100%" height={Math.max(usage_by_source.length * 50, 120)}>
            <BarChart layout="vertical" data={usage_by_source}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={formatTokens} />
              <YAxis type="category" dataKey="source" tick={{ fontSize: 12 }} width={120} />
              <Tooltip formatter={(value: number) => formatTokens(value)} />
              <Bar dataKey="tokens" fill="#f97316" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-center text-scurry-gray-muted py-4">No usage data yet</p>
        )}
      </div>

      {/* Recent Activity table */}
      <div className="bg-white rounded-lg border border-scurry-gray-border overflow-hidden">
        <div className="px-4 py-3 border-b border-scurry-gray-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-scurry-espresso">Recent Activity</h2>
          <span className="text-xs text-scurry-latte">{recent_activity.length} total</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-scurry-foam text-left text-xs text-scurry-latte uppercase tracking-wider">
                <th className="px-4 py-3">Workflow</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Tokens</th>
                <th className="px-4 py-3">API Cost</th>
                <th className="px-4 py-3">Acorns</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Date &amp; Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-scurry-gray-border">
              {pagedActivity.length > 0 ? (
                pagedActivity.map((item, idx) => {
                  const statusClass =
                    item.status === 'completed'
                      ? 'bg-green-100 text-green-700'
                      : item.status === 'failed'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-yellow-100 text-yellow-700'
                  const typeClass =
                    item.type === 'pipeline'
                      ? 'bg-blue-100 text-blue-700'
                      : 'bg-purple-100 text-purple-700'
                  return (
                    <tr key={`${item.type}-${activityPage}-${idx}`} className="hover:bg-scurry-foam/50">
                      <td className="px-4 py-3 font-medium text-scurry-espresso">{item.workflow_name}</td>
                      <td className="px-4 py-3">
                        <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${typeClass}`}>
                          {item.label}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${statusClass}`}>
                          {item.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-scurry-espresso">
                        <span>{formatTokens(item.total_tokens)}</span>
                        <span className="block text-[10px] text-scurry-latte">
                          {formatTokens(item.total_prompt_tokens)} in / {formatTokens(item.total_completion_tokens)} out
                        </span>
                      </td>
                      <td className="px-4 py-3 text-scurry-espresso">
                        {formatCost(item.cost)}
                        {item.actual_cost != null && item.actual_cost !== item.cost && (
                          <span className="block text-[10px] text-scurry-latte">
                            actual {formatCost(item.actual_cost)}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-amber-700 font-medium">
                        {item.cost > 0 ? <><AcornIcon className="w-3.5 h-3.5" /> {Math.round(item.cost / 0.01).toLocaleString()}</> : '—'}
                      </td>
                      <td className="px-4 py-3 text-scurry-latte text-xs">{item.model || '—'}</td>
                      <td className="px-4 py-3 text-scurry-latte">{formatDateTime(item.started_at)}</td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-scurry-gray-muted">
                    No activity yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-scurry-gray-border flex items-center justify-between">
            <span className="text-xs text-scurry-latte">
              Page {activityPage + 1} of {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setActivityPage((p) => Math.max(0, p - 1))}
                disabled={activityPage === 0}
                className="p-1.5 rounded-md border border-scurry-gray-border text-scurry-latte hover:bg-scurry-foam disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setActivityPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={activityPage >= totalPages - 1}
                className="p-1.5 rounded-md border border-scurry-gray-border text-scurry-latte hover:bg-scurry-foam disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
