import React from 'react'
import { useAuth } from '@/contexts/AuthContext'

const SettingsApiKeys: React.FC = () => {
  const { user } = useAuth()
  const role = user?.role || 'member'
  const plan = user?.account?.plan_tier || 'oak'

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔑</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Buried Keys</div>
        <div className="text-sm text-gray-500 max-w-sm mx-auto">
          These keys are buried deep — only Owners and Admins know where! If you need API access, time to send your best puppy-eyes Slack to an Admin.
        </div>
      </div>
    )
  }

  if (plan === 'seedling' || plan === 'oak') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-[40px] mb-3">🔑</div>
        <div className="font-bold text-[15px] mb-1.5">API Access requires Redwood or above</div>
        <div className="text-sm text-gray-500 max-w-sm mx-auto mb-5">
          Upgrade to Redwood to unlock API access and build custom integrations.
        </div>
        <button className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors">
          Upgrade to Redwood →
        </button>
      </div>
    )
  }

  return (
    <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900">
            <span className="text-scurry-orange">🔑</span> API Keys
          </div>
          <p className="text-sm text-gray-500">Scoped to your organization. Never share publicly.</p>
        </div>
        <button className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors">
          + Generate New Key
        </button>
      </div>
      <p className="text-sm text-gray-500 text-center py-8">
        API key management coming soon.
      </p>
    </div>
  )
}

export default SettingsApiKeys
