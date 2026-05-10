import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { billingApi, teamApi } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { Loader2 } from 'lucide-react'
import { AcornIcon } from '@/components/ui/acorn-icon'

const SettingsAcorns: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const role = user?.role || 'member'

  const [threshold, setThreshold] = useState('100')
  const [allocations, setAllocations] = useState<Record<number, string>>({})
  const [txPage, setTxPage] = useState(0)
  const txPerPage = 10

  const isAdmin = role === 'owner' || role === 'admin'

  const { data: allocationData, isLoading: allocationLoading } = useQuery({
    queryKey: ['acorn-allocation'],
    queryFn: () => teamApi.getAllocationMode().then((r) => r.data),
    enabled: isAdmin,
  })

  const allocationMode = allocationData?.mode || 'shared'
  const totalBalance = allocationData?.total_balance || 0
  const allocationMembers = allocationData?.members || []

  // Initialize allocation inputs from server data
  useEffect(() => {
    if (allocationMembers.length > 0) {
      const initial: Record<number, string> = {}
      allocationMembers.forEach((m: any) => {
        initial[m.user_id] = m.locked_acorn_allocation != null ? String(m.locked_acorn_allocation) : ''
      })
      setAllocations(initial)
    }
  }, [allocationData])

  const setModeMutation = useMutation({
    mutationFn: (mode: string) => teamApi.setAllocationMode(mode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['acorn-allocation'] })
      toast({ title: 'Allocation mode updated' })
    },
    onError: (err: any) => {
      toast({
        title: 'Error',
        description: err.response?.data?.detail || 'Failed to update allocation mode',
        variant: 'destructive',
      })
    },
  })

  const allocateMutation = useMutation({
    mutationFn: ({ userId, amount }: { userId: number; amount: number }) =>
      teamApi.allocateAcorns(userId, amount),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['acorn-allocation'] })
      toast({ title: 'Allocation saved' })
    },
    onError: (err: any) => {
      toast({
        title: 'Error',
        description: err.response?.data?.detail || 'Failed to allocate acorns',
        variant: 'destructive',
      })
    },
  })

  const { data: transactionsData, isLoading: txLoading } = useQuery({
    queryKey: ['acorn-transactions', txPage],
    queryFn: () => billingApi.getTransactions(txPerPage, txPage * txPerPage).then((res) => res.data),
  })

  const transactions = Array.isArray(transactionsData)
    ? transactionsData
    : transactionsData?.transactions ?? []
  const txTotal = transactionsData?.total ?? 0
  const txHasMore = transactionsData?.has_more ?? false

  // Reset to first page if current page is out of bounds
  useEffect(() => {
    if (transactionsData && transactions.length === 0 && txPage > 0) {
      setTxPage(0)
    }
  }, [transactionsData, transactions.length, txPage])

  const { data: members } = useQuery({
    queryKey: ['team-members'],
    queryFn: () => teamApi.listMembers().then((r) => r.data),
    enabled: isAdmin,
  })

  const getInitials = (name: string) =>
    name
      .split(' ')
      .map((n: string) => n[0])
      .join('')
      .toUpperCase()

  const modeOptions = [
    {
      value: 'shared',
      title: 'Shared Pool',
      desc: 'All team members draw from one organization-wide balance.',
    },
    {
      value: 'locked',
      title: 'Locked Per Seat',
      desc: 'Each user has their own individual Acorn allocation.',
    },
  ]

  // Calculate allocation stats for locked mode
  const totalAllocated = allocationMembers.reduce(
    (sum: number, m: any) => sum + (m.locked_acorn_allocation || 0),
    0
  )
  const remaining = totalBalance - totalAllocated

  if (!isAdmin) {
    // Member view: show allocation status + own transactions
    const isLocked = user?.account?.acorn_allocation_mode === 'locked'
    const myAllocation = user?.locked_acorn_allocation
    const myBalance = user?.locked_acorn_balance

    return (
      <div className="space-y-5">
        {/* Allocation Status */}
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">⚙️</span> Your Acorn Allocation
          </div>
          {isLocked && myAllocation != null ? (
            <>
              <p className="text-sm text-gray-500 mb-4">
                You have a personal Acorn budget that resets each billing cycle.
              </p>
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="bg-scurry-orange-light rounded-lg p-4 text-center">
                  <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Allocated / Cycle</div>
                  <div className="text-xl font-bold text-scurry-orange flex items-center justify-center gap-1">
                    {Math.round(myAllocation)} <AcornIcon className="w-4 h-4" />
                  </div>
                </div>
                <div className={`rounded-lg p-4 text-center ${(myBalance ?? 0) < 10 ? 'bg-red-50' : 'bg-green-50'}`}>
                  <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Remaining</div>
                  <div className={`text-xl font-bold flex items-center justify-center gap-1 ${(myBalance ?? 0) < 10 ? 'text-red-600' : 'text-green-600'}`}>
                    {Math.round(myBalance ?? 0)} <AcornIcon className="w-4 h-4" />
                  </div>
                </div>
              </div>
              {myAllocation > 0 && (
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${(myBalance ?? 0) < 10 ? 'bg-red-400' : 'bg-scurry-orange'}`}
                    style={{ width: `${Math.max(0, Math.min(((myBalance ?? 0) / myAllocation) * 100, 100))}%` }}
                  />
                </div>
              )}
            </>
          ) : (
            <>
              <p className="text-sm text-gray-500 mb-3">
                Your organization uses a shared Acorn pool. All team members draw from the same balance.
              </p>
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                Shared pool balance: <strong>{Math.round(user?.account?.acorn_balance ?? 0)}</strong> Acorns
              </div>
            </>
          )}
        </div>

        {/* Own Transactions */}
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-4">
            <span className="text-scurry-orange">📋</span> Your Acorn Usage
          </div>
          {txLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-scurry-orange" />
            </div>
          ) : transactions.length > 0 ? (
            <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    {['Date', 'Type', 'Amount', 'Description'].map((h) => (
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
                  {transactions.map((tx: any, i: number) => (
                    <tr key={tx.id || i}>
                      <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500 text-xs">
                        {tx.created_at
                          ? new Date(tx.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                          : '—'}
                      </td>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        {tx.type || '—'}
                      </td>
                      <td className={`px-2.5 py-3 border-b border-gray-200 font-semibold ${(tx.amount ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {(tx.amount ?? 0) >= 0 ? '+' : ''}{Number(tx.amount ?? 0).toFixed(2)} <AcornIcon className="w-3 h-3" />
                      </td>
                      <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500">
                        {tx.description || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {txTotal > txPerPage && (
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
                <span className="text-xs text-gray-500">
                  {Math.min(txPage * txPerPage + 1, txTotal)}–{Math.min((txPage + 1) * txPerPage, txTotal)} of {txTotal}
                </span>
                <div className="flex gap-2">
                  <button onClick={() => setTxPage((p) => Math.max(0, p - 1))} disabled={txPage === 0}
                    className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    Previous
                  </button>
                  <button onClick={() => setTxPage((p) => p + 1)} disabled={!txHasMore}
                    className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    Next
                  </button>
                </div>
              </div>
            )}
            </>
          ) : (
            <p className="text-sm text-gray-500 text-center py-4">No usage yet.</p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Allocation Mode */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">⚙️</span> Acorn Allocation Mode
        </div>
        <p className="text-sm text-gray-500 mb-4">Choose how Acorns are shared across your team.</p>

        {modeOptions.map((opt) => (
          <div
            key={opt.value}
            onClick={() => setModeMutation.mutate(opt.value)}
            className={`flex items-start gap-3 p-4 border-[1.5px] rounded-[9px] mb-2.5 cursor-pointer transition-all ${
              allocationMode === opt.value
                ? 'border-scurry-orange bg-scurry-orange-light'
                : 'border-gray-200 bg-white hover:bg-gray-50'
            }`}
          >
            <div
              className={`w-[18px] h-[18px] rounded-full border-2 flex items-center justify-center flex-shrink-0 mt-0.5 ${
                allocationMode === opt.value ? 'border-scurry-orange' : 'border-gray-200'
              }`}
            >
              {allocationMode === opt.value && (
                <div className="w-2 h-2 rounded-full bg-scurry-orange" />
              )}
            </div>
            <div>
              <div className="font-semibold text-sm">{opt.title}</div>
              <div className="text-sm text-gray-500 mt-0.5">{opt.desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Per-User Allocation — only in locked mode */}
      {allocationMode === 'locked' && (
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">🔒</span> Per-User Allocation
          </div>
          <p className="text-sm text-gray-500 mb-4">
            Distribute your Acorn pool across team members. Each member can only spend their allocated amount.
          </p>

          {/* Pool Summary */}
          <div className="grid grid-cols-3 gap-3 mb-5">
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Total Pool</div>
              <div className="text-lg font-bold text-gray-900 flex items-center justify-center gap-1">
                {totalBalance.toFixed(0)} <AcornIcon className="w-4 h-4" />
              </div>
            </div>
            <div className="bg-scurry-orange-light rounded-lg p-3 text-center">
              <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Allocated</div>
              <div className="text-lg font-bold text-scurry-orange flex items-center justify-center gap-1">
                {totalAllocated.toFixed(0)} <AcornIcon className="w-4 h-4" />
              </div>
            </div>
            <div className={`rounded-lg p-3 text-center ${remaining < 0 ? 'bg-red-50' : 'bg-green-50'}`}>
              <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wide mb-0.5">Remaining</div>
              <div className={`text-lg font-bold flex items-center justify-center gap-1 ${remaining < 0 ? 'text-red-600' : 'text-green-600'}`}>
                {remaining.toFixed(0)} <AcornIcon className="w-4 h-4" />
              </div>
            </div>
          </div>

          {/* Allocation progress bar */}
          <div className="mb-5">
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${totalAllocated > totalBalance ? 'bg-red-400' : 'bg-scurry-orange'}`}
                style={{ width: `${Math.min((totalAllocated / Math.max(totalBalance, 1)) * 100, 100)}%` }}
              />
            </div>
          </div>

          {allocationLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="w-5 h-5 animate-spin text-scurry-orange" />
            </div>
          ) : (
            <div className="space-y-3">
              {allocationMembers.map((m: any) => {
                const member = members?.find((mem: any) => mem.id === m.user_id)
                const displayName = m.full_name || m.email || member?.full_name || member?.email || 'Unknown'
                return (
                  <div
                    key={m.user_id}
                    className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg"
                  >
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-scurry-orange to-scurry-latte flex items-center justify-center text-[11px] text-white font-bold flex-shrink-0">
                      {getInitials(displayName)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">{displayName}</div>
                      <div className="text-xs text-gray-500">
                        {m.locked_acorn_balance != null && m.locked_acorn_allocation != null ? (
                          <span>
                            {Math.round(m.locked_acorn_balance)} of {Math.round(m.locked_acorn_allocation)} remaining
                          </span>
                        ) : (
                          m.email
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <input
                          type="number"
                          min="0"
                          step="1"
                          className="w-[100px] px-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange text-right pr-7"
                          value={allocations[m.user_id] ?? ''}
                          onChange={(e) =>
                            setAllocations((prev) => ({ ...prev, [m.user_id]: e.target.value }))
                          }
                          placeholder="0"
                        />
                        <div className="absolute right-2 top-1/2 -translate-y-1/2">
                          <AcornIcon className="w-3.5 h-3.5" />
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          const amount = parseFloat(allocations[m.user_id] || '0')
                          if (isNaN(amount) || amount < 0) {
                            toast({ title: 'Invalid amount', variant: 'destructive' })
                            return
                          }
                          allocateMutation.mutate({ userId: m.user_id, amount })
                        }}
                        disabled={allocateMutation.isPending}
                        className="px-3 py-1.5 bg-scurry-orange text-white text-xs font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
                      >
                        {allocateMutation.isPending ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          'Save'
                        )}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Usage by Team Member (shared mode) */}
      {allocationMode === 'shared' && members && members.length > 1 && (
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">📊</span> Team Members
          </div>
          <p className="text-sm text-gray-500 mb-4">
            All members share the organization's Acorn pool ({totalBalance.toFixed(0)} <AcornIcon className="w-3 h-3 inline" />).
          </p>

          {members?.map((m: any) => (
            <div key={m.id} className="mb-4 last:mb-0">
              <div className="flex justify-between items-center mb-1.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-[30px] h-[30px] rounded-full bg-gradient-to-br from-scurry-orange to-scurry-latte flex items-center justify-center text-[11px] text-white font-bold flex-shrink-0">
                    {getInitials(m.full_name || m.email)}
                  </div>
                  <span className="font-medium text-sm">{m.full_name || m.email}</span>
                </div>
                <span className="text-[11px] font-bold text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full capitalize">
                  {m.role}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Low Balance Alert */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">🔔</span> Low Balance Alert
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Get notified when your Acorn balance falls below this threshold.
        </p>
        <div className="flex items-center gap-3">
          <input
            type="number"
            className="w-[120px] px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
            value={threshold}
            onChange={(e) => setThreshold(e.target.value)}
          />
          <span className="text-sm text-gray-500">Acorns remaining</span>
        </div>
        <div className="mt-3.5">
          <button
            onClick={() => toast({ title: 'Alert threshold saved', description: `You'll be notified below ${threshold} Acorns.` })}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors"
          >
            Save Alert
          </button>
        </div>
      </div>

      {/* Recent Transactions */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-4">
          <span className="text-scurry-orange">📋</span> Recent Acorn Transactions
        </div>

        {txLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-scurry-orange" />
          </div>
        ) : transactions.length > 0 ? (
          <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  {['Date', 'User', 'Type', 'Amount', 'Description'].map((h) => (
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
                {transactions.map((tx: any, i: number) => (
                  <tr key={tx.id || i}>
                    <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500 text-xs">
                      {tx.created_at
                        ? new Date(tx.created_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                          })
                        : '—'}
                    </td>
                    <td className="px-2.5 py-3 border-b border-gray-200 text-xs text-gray-700">
                      {tx.user_name || '—'}
                    </td>
                    <td className="px-2.5 py-3 border-b border-gray-200">
                      {tx.type || tx.transaction_type || '—'}
                    </td>
                    <td
                      className={`px-2.5 py-3 border-b border-gray-200 font-semibold ${
                        (tx.amount ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}
                    >
                      {(tx.amount ?? 0) >= 0 ? '+' : ''}
                      {Number(tx.amount ?? 0).toFixed(2)} <AcornIcon className="w-3 h-3" />
                    </td>
                    <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500">
                      {tx.description || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Pagination */}
          {txTotal > txPerPage && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
              <span className="text-xs text-gray-500">
                {Math.min(txPage * txPerPage + 1, txTotal)}–{Math.min((txPage + 1) * txPerPage, txTotal)} of {txTotal}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setTxPage((p) => Math.max(0, p - 1))}
                  disabled={txPage === 0}
                  className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <button
                  onClick={() => setTxPage((p) => p + 1)}
                  disabled={!txHasMore}
                  className="px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
          </>
        ) : (
          <p className="text-sm text-gray-500 text-center py-4">No transactions yet.</p>
        )}
      </div>
    </div>
  )
}

export default SettingsAcorns
