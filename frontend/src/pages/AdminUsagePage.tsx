import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { DollarSign, Coins, Zap } from 'lucide-react'
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { adminApi } from '@/lib/api'
import { formatCost } from '@/lib/cost'

const USER_COLORS = [
  '#f97316', '#3b82f6', '#10b981', '#8b5cf6', '#ef4444',
  '#06b6d4', '#f59e0b', '#ec4899', '#14b8a6', '#6366f1',
]

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatShortDate(iso: string): string {
  // Parse YYYY-MM-DD as local date to avoid UTC-to-local timezone shift
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export default function AdminUsagePage() {
  const [days, setDays] = useState(30)

  const { data: usage, isLoading } = useQuery({
    queryKey: ['admin', 'usage', days],
    queryFn: () => adminApi.getUsageOverTime(days).then((r) => r.data),
  })

  const totalCost = useMemo(() => {
    if (!usage?.daily_stats) return 0
    return usage.daily_stats.reduce((sum, d) => sum + (d.cost ?? 0), 0)
  }, [usage])

  const totalActualCost = useMemo(() => {
    if (!usage?.daily_stats) return 0
    return usage.daily_stats.reduce((sum, d) => sum + (d.actual_cost ?? 0), 0)
  }, [usage])

  const totalTokens = useMemo(() => {
    if (!usage?.daily_stats) return 0
    return usage.daily_stats.reduce((sum, d) => sum + d.tokens, 0)
  }, [usage])

  const totalExecutions = useMemo(() => {
    if (!usage?.daily_stats) return 0
    return usage.daily_stats.reduce((sum, d) => sum + d.executions, 0)
  }, [usage])

  const costChartData = useMemo(() => {
    if (!usage?.daily_stats) return []
    return usage.daily_stats.map((d) => ({
      date: formatShortDate(d.date),
      cost: d.cost ?? 0,
      actual_cost: d.actual_cost ?? 0,
    }))
  }, [usage])

  const userEmails = useMemo(() => {
    if (!usage?.daily_stats) return []
    const names = new Set<string>()
    usage.daily_stats.forEach((d) =>
      Object.keys(d.by_user).forEach((u) => names.add(u))
    )
    return Array.from(names)
  }, [usage])

  const tokenChartData = useMemo(() => {
    if (!usage?.daily_stats) return []
    return usage.daily_stats.map((d) => ({
      date: formatShortDate(d.date),
      ...Object.fromEntries(
        Object.entries(d.by_user).map(([user, stats]) => [`${user}_tokens`, stats.tokens])
      ),
    }))
  }, [usage])

  const executionChartData = useMemo(() => {
    if (!usage?.daily_stats) return []
    return usage.daily_stats.map((d) => ({
      date: formatShortDate(d.date),
      executions: d.executions,
    }))
  }, [usage])

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
            className="pb-3 px-1 text-sm font-medium border-b-2 border-transparent text-scurry-latte hover:text-scurry-espresso transition-colors"
          >
            Overview
          </Link>
          <span className="pb-3 px-1 text-sm font-medium border-b-2 border-scurry-orange text-scurry-orange">
            Usage &amp; Cost
          </span>
          <Link
            to="/admin/models"
            className="pb-3 px-1 text-sm font-medium border-b-2 border-transparent text-scurry-latte hover:text-scurry-espresso transition-colors"
          >
            Models
          </Link>
        </nav>
      </div>

      <div className="flex gap-2">
        {[
          { label: '7d', value: 7 },
          { label: '30d', value: 30 },
          { label: '90d', value: 90 },
        ].map((opt) => (
          <button
            key={opt.value}
            onClick={() => setDays(opt.value)}
            className={`px-3 py-1.5 text-sm rounded-md border transition-colors ${
              days === opt.value
                ? 'bg-scurry-orange text-white border-scurry-orange'
                : 'bg-white text-scurry-latte border-scurry-gray-border hover:border-scurry-orange'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
        </div>
      ) : usage && usage.daily_stats.length > 0 ? (
        <>
          <div className="grid grid-cols-3 gap-4">
            {[
              {
                label: 'Total Cost',
                value: formatCost(totalCost),
                sub: totalActualCost > 0 ? `Anthropic: ${formatCost(totalActualCost)}` : null,
                icon: DollarSign,
                color: 'text-orange-600 bg-orange-50',
              },
              { label: 'Total Tokens', value: formatTokens(totalTokens), sub: null, icon: Coins, color: 'text-blue-600 bg-blue-50' },
              { label: 'Total Executions', value: totalExecutions, sub: null, icon: Zap, color: 'text-green-600 bg-green-50' },
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

          <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
            <h3 className="text-sm font-semibold text-scurry-espresso mb-4">Daily Cost Breakdown</h3>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={costChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v: number) => `$${v.toFixed(2)}`} />
                <Tooltip formatter={(value: number) => `$${value.toFixed(4)}`} />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="cost"
                  name="Billable"
                  stroke="#f97316"
                  fill="#f97316"
                  fillOpacity={0.4}
                />
                <Area
                  type="monotone"
                  dataKey="actual_cost"
                  name="Actual (Anthropic)"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
            <h3 className="text-sm font-semibold text-scurry-espresso mb-4">Daily Token Usage by User</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={tokenChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={formatTokens} />
                <Tooltip formatter={(value: number) => formatTokens(value)} />
                <Legend />
                {userEmails.map((userEmail, i) => (
                  <Line
                    key={userEmail}
                    type="monotone"
                    dataKey={`${userEmail}_tokens`}
                    name={userEmail}
                    stroke={USER_COLORS[i % USER_COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white rounded-lg border border-scurry-gray-border p-4">
            <h3 className="text-sm font-semibold text-scurry-espresso mb-4">Daily Executions</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={executionChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="executions" name="Executions" fill="#f97316" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      ) : (
        <div className="bg-white rounded-lg border border-scurry-gray-border p-8 text-center text-scurry-gray-muted">
          No usage data for the selected period
        </div>
      )}
    </div>
  )
}
