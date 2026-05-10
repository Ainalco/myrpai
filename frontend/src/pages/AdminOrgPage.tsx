import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Building2, Users, Zap, DollarSign } from 'lucide-react'
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

export default function AdminOrgPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'org', id],
    queryFn: () => adminApi.getOrgStats(Number(id)).then((r) => r.data),
    enabled: !!id,
  })

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />
        <div className="relative z-10">
          <button
            onClick={() => navigate('/admin')}
            className="flex items-center gap-1.5 text-sm text-scurry-latte hover:text-scurry-espresso mb-3 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Admin Overview
          </button>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-scurry-orange/10 rounded-lg">
              <Building2 className="h-6 w-6 text-scurry-orange" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-scurry-espresso font-display">
                {data?.org.name ?? 'Organization'}
              </h1>
              {data?.org.domain && (
                <p className="text-sm text-scurry-latte mt-0.5">{data.org.domain}</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <div className="border-b border-scurry-gray-border">
        <nav className="flex gap-4">
          <Link
            to="/admin"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
          >
            Overview
          </Link>
          <span className="pb-3 px-1 text-sm font-medium border-b-2 border-scurry-orange text-scurry-orange">
            Organization
          </span>
        </nav>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
        </div>
      ) : data ? (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                label: 'Members',
                value: data.members.length as React.ReactNode,
                sub: null as string | null,
                icon: Users,
                color: 'text-blue-600 bg-blue-50',
              },
              {
                label: 'Total Tokens',
                value: formatTokens(data.total_tokens),
                sub: null,
                icon: Zap,
                color: 'text-green-600 bg-green-50',
              },
              {
                label: 'API Cost',
                value: formatCost(data.total_cost),
                sub: data.total_actual_cost != null && data.total_actual_cost !== data.total_cost
                  ? `Anthropic: ${formatCost(data.total_actual_cost)}` : null,
                icon: DollarSign,
                color: 'text-orange-600 bg-scurry-orange-light',
              },
              {
                label: 'Acorn Balance',
                value: (
                  <span className="flex items-center gap-1">
                    <AcornIcon className="w-5 h-5" />
                    {Math.round(data.acorn_balance).toLocaleString()}
                  </span>
                ),
                sub: null,
                icon: DollarSign,
                color: 'text-amber-700 bg-amber-50',
              },
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

          {/* Plan + allocation mode badges */}
          <div className="flex items-center gap-3">
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
              data.plan === 'redwood' ? 'text-green-700 bg-green-50 border border-green-200' :
              data.plan === 'oak' ? 'text-scurry-orange bg-scurry-orange-light border border-scurry-orange/20' :
              data.plan === 'seedling' ? 'text-gray-600 bg-gray-100 border border-gray-200' :
              'text-scurry-latte bg-gray-50 border border-gray-200'
            }`}>
              {data.plan || 'No plan'}
            </span>
            <span className="text-xs text-scurry-latte bg-gray-50 border border-gray-200 px-2.5 py-1 rounded-full font-medium">
              {data.allocation_mode === 'locked' ? 'Locked per seat' : 'Shared pool'}
            </span>
          </div>

          {/* Member table */}
          <div className="bg-white rounded-lg border border-scurry-gray-border overflow-hidden">
            <div className="px-4 py-3 border-b border-scurry-gray-border">
              <h2 className="text-sm font-semibold text-scurry-espresso">Members</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-scurry-foam text-left text-xs text-scurry-latte uppercase tracking-wider">
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3">Role</th>
                    <th className="px-4 py-3">Workflows</th>
                    <th className="px-4 py-3">Executions</th>
                    <th className="px-4 py-3">Tokens</th>
                    <th className="px-4 py-3">API Cost</th>
                    <th className="px-4 py-3">Acorns Spent</th>
                    <th className="px-4 py-3">Balance</th>
                    <th className="px-4 py-3">Last Active</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-scurry-gray-border">
                  {data.members.map((member) => (
                    <tr
                      key={member.id}
                      className="hover:bg-scurry-foam/50 cursor-pointer"
                      onClick={() => navigate(`/admin/user/${member.id}`)}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <span className="font-medium text-scurry-espresso">{member.full_name || member.email}</span>
                          {member.is_superadmin && (
                            <span className="ml-2 text-[10px] bg-scurry-orange text-white px-1.5 py-0.5 rounded-full font-medium">
                              Admin
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-scurry-gray-muted">{member.email}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${
                          member.role === 'owner' ? 'text-purple-700 bg-purple-50' :
                          member.role === 'admin' ? 'text-blue-700 bg-blue-50' :
                          'text-gray-600 bg-gray-100'
                        }`}>
                          {member.role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-scurry-espresso">{member.workflow_count}</td>
                      <td className="px-4 py-3 text-scurry-espresso">{member.execution_count}</td>
                      <td className="px-4 py-3">
                        <span className="font-medium text-scurry-espresso">{formatTokens(member.total_tokens)}</span>
                        <div className="text-[10px] text-scurry-gray-muted">
                          {formatTokens(member.total_prompt_tokens)} in / {formatTokens(member.total_completion_tokens)} out
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-medium text-scurry-espresso">
                          {formatCost(member.cost)}
                        </span>
                        {member.actual_cost != null && member.actual_cost !== member.cost && (
                          <div className="text-[10px] text-scurry-gray-muted">
                            actual {formatCost(member.actual_cost)}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-medium text-amber-700 flex items-center gap-1">
                          <AcornIcon className="w-3.5 h-3.5" />
                          {Math.round(member.acorns_spent || 0).toLocaleString()}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-medium text-scurry-espresso">
                          {Math.round(member.acorn_balance || 0).toLocaleString()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-scurry-latte">{formatDate(member.last_active)}</td>
                    </tr>
                  ))}
                  {data.members.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-scurry-gray-muted">
                        No members found
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="text-center py-12 text-scurry-gray-muted">Organization not found</div>
      )}
    </div>
  )
}
