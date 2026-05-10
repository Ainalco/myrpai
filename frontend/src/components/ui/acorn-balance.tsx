import { useAuth } from '@/contexts/AuthContext'
import { useNavigate } from 'react-router-dom'

export function AcornBalance() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (!user?.account) return null

  // In locked allocation mode, show the user's personal balance out of their allocation
  const isLocked = user.account.acorn_allocation_mode === 'locked'
  const hasAllocation = isLocked && user.locked_acorn_balance != null && user.locked_acorn_allocation != null
  const balance = hasAllocation ? user.locked_acorn_balance! : user.account.acorn_balance
  const allocation = hasAllocation ? user.locked_acorn_allocation : null
  const isLow = balance < 50

  return (
    <button
      onClick={() => navigate('/settings/billing')}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
        isLow
          ? 'bg-red-100 text-red-700 hover:bg-red-200'
          : 'bg-amber-100 text-amber-700 hover:bg-amber-200'
      }`}
      title={hasAllocation ? `${Math.round(balance)} of ${Math.round(allocation!)} Acorns remaining this cycle` : 'Organization Acorn balance'}
    >
      <img src="/favicon.svg" alt="acorn" className="w-4 h-4" />
      <span>
        {Math.round(balance).toLocaleString()}
        {allocation != null && (
          <span className="opacity-60">/{Math.round(allocation).toLocaleString()}</span>
        )}
      </span>
    </button>
  )
}
