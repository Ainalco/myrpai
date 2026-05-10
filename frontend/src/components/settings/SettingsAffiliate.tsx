import React, { useState } from 'react'
import { useAuth } from '@/contexts/AuthContext'

const SettingsAffiliate: React.FC = () => {
  const { user } = useAuth()
  const role = user?.role || 'member'
  const [copied, setCopied] = useState(false)

  if (role !== 'owner') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          The Affiliate Program is available to the Organization Owner only.
        </div>
      </div>
    )
  }

  const copy = () => {
    navigator.clipboard.writeText('https://scurry.ai/ref/your-org')
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="bg-gradient-to-br from-scurry-espresso to-scurry-latte rounded-[10px] p-6 text-white">
        <div className="font-bold text-base mb-1">🐿️ The Referral Nut Stash</div>
        <div className="text-sm opacity-80 mb-5">
          Earn 15% lifetime commission on every account you refer. No cap, no expiry.
        </div>
        <div className="grid grid-cols-3 gap-3.5">
          {[
            ['Total Referred', '0 Accounts'],
            ['Active Subscribers', '0'],
            ['Lifetime Earnings', '$0.00'],
          ].map(([label, value]) => (
            <div
              key={label}
              className="bg-white/10 rounded-[9px] p-3.5"
            >
              <div className="text-xs opacity-70 mb-1">{label}</div>
              <div className="text-[22px] font-extrabold">{value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Referral Link */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">🔗</span> Your Referral Link
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Share this link. Earn 15% of every payment they make, forever.
        </p>
        <div className="flex">
          <div className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 border-r-0 rounded-l-lg text-sm text-gray-500 font-mono truncate">
            https://scurry.ai/ref/your-org
          </div>
          <button
            onClick={copy}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-r-lg hover:bg-scurry-orange-hover transition-colors min-w-[110px] justify-center"
          >
            {copied ? '✓ Copied!' : 'Copy Link'}
          </button>
        </div>
      </div>

      {/* Commission History */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-4">
          <span className="text-scurry-orange">💰</span> Commission History
        </div>
        <p className="text-sm text-gray-500 text-center py-8">
          No commissions yet. Share your referral link to get started.
        </p>
      </div>
    </div>
  )
}

export default SettingsAffiliate
