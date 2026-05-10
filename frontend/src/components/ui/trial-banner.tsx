import { useAuth } from '@/contexts/AuthContext'
import { useNavigate } from 'react-router-dom'

export function TrialBanner() {
  const { user } = useAuth()
  const navigate = useNavigate()

  if (!user?.account) return null
  const { status, trial_ends_at } = user.account
  if (status === 'active') return null

  let message = ''
  let bgClass = ''

  if (status === 'trialing' && trial_ends_at) {
    const daysLeft = Math.ceil((new Date(trial_ends_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    if (daysLeft <= 0) {
      message = 'Your free trial has expired. You are now on the free Seedling plan.'
      bgClass = 'bg-red-600'
    } else {
      message = `You're enjoying a free Redwood trial — all features unlocked! ${daysLeft} day${daysLeft !== 1 ? 's' : ''} remaining.`
      bgClass = 'bg-scurry-orange'
    }
  } else if (status === 'past_due') {
    message = 'Payment failed. Please update your payment method to continue using Scurry.'
    bgClass = 'bg-red-600'
  } else if (status === 'suspended') {
    message = 'Your account is suspended. Please reactivate your subscription.'
    bgClass = 'bg-red-700'
  } else if (status === 'cancelled') {
    message = 'Your subscription has been cancelled. Export your data before access ends.'
    bgClass = 'bg-gray-700'
  }

  if (!message) return null

  return (
    <div className={`${bgClass} text-white text-sm text-center py-2 px-4`}>
      {message}{' '}
      <button onClick={() => navigate('/settings/billing')} className="underline font-medium hover:no-underline">
        {status === 'cancelled' ? 'Export data' : 'Choose a plan'}
      </button>
    </div>
  )
}
