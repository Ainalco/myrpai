import React from 'react'
import { Link, useLocation, Outlet } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

interface NavItem {
  id: string
  label: string
  icon: string
  path: string
  planTag?: string
  ownerOnly?: boolean
}

interface NavGroup {
  group: string
  items: NavItem[]
}

const NAV: NavGroup[] = [
  {
    group: 'Personal',
    items: [{ id: 'profile', label: 'Profile', icon: '👤', path: '/settings' }],
  },
  {
    group: 'Organization',
    items: [
      { id: 'organization', label: 'Organization', icon: '🏢', path: '/settings/organization' },
      { id: 'team', label: 'Team', icon: '👥', path: '/settings/team' },
    ],
  },
  {
    group: 'Billing & Credits',
    items: [
      { id: 'billing', label: 'The Treasury', icon: '💳', path: '/settings/billing' },
      { id: 'acorns', label: 'Acorn Management', icon: '🥜', path: '/settings/acorns' },
    ],
  },
  {
    group: 'Connections',
    items: [
      { id: 'integrations', label: 'Integrations', icon: '🔌', path: '/settings/integrations' },
      { id: 'apikeys', label: 'API Keys', icon: '🔑', path: '/settings/api-keys', planTag: 'Redwood+' },
    ],
  },
  {
    group: 'Growth',
    items: [
      { id: 'affiliate', label: 'Affiliate Program', icon: '💸', path: '/settings/affiliate', ownerOnly: true },
    ],
  },
  {
    group: 'Security',
    items: [{ id: 'auditlog', label: 'Audit Log', icon: '📋', path: '/settings/audit-log' }],
  },
]

const PAGE_TITLES: Record<string, [string, string]> = {
  '/settings': ['Profile', 'Your personal details and email signature'],
  '/settings/organization': ['Organization', 'Company settings and internal domains'],
  '/settings/team': ['Team', 'Manage members and invitations'],
  '/settings/billing': ['The Treasury', 'Subscription, plans and billing'],
  '/settings/acorns': ['Acorn Management', 'Credits, usage and allocation'],
  '/settings/integrations': ['Integrations', 'Manage your API keys and integrations'],
  '/settings/api-keys': ['API Keys', 'External integration credentials'],
  '/settings/affiliate': ['Affiliate Program', 'Referral link and commission history'],
  '/settings/audit-log': ['Audit Log', 'Account activity and security events'],
}

const SettingsLayout: React.FC = () => {
  const location = useLocation()
  const { user } = useAuth()
  const role = user?.role || 'member'

  const canSee = (item: { ownerOnly?: boolean }) => {
    if (item.ownerOnly && role !== 'owner') return false
    return true
  }

  const [title, subtitle] = PAGE_TITLES[location.pathname] || ['Settings', '']

  return (
    <div className="flex -mx-2 sm:-mx-4 lg:-mx-6 -my-3 sm:-my-4 min-h-[calc(100vh-4rem)]">
      {/* Settings Sub-Sidebar */}
      <div className="w-52 bg-white border-r border-gray-200 flex-shrink-0 overflow-y-auto hidden md:flex md:flex-col">
        <div className="px-4 pt-5 pb-3 border-b border-gray-200">
          <div className="text-sm font-bold text-gray-900">Settings</div>
        </div>
        <div className="px-3 py-2 flex-1">
          {NAV.map((group) => (
            <div key={group.group} className="mb-3">
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-wider px-2 py-1">
                {group.group}
              </div>
              {group.items.filter(canSee).map((item) => {
                const active = location.pathname === item.path
                return (
                  <Link
                    key={item.id}
                    to={item.path}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded-lg mb-0.5 text-[13px] transition-colors ${
                      active
                        ? 'bg-scurry-orange-light font-semibold text-scurry-orange'
                        : 'text-gray-900 hover:bg-gray-50'
                    }`}
                  >
                    <span className="text-sm w-4 text-center">{item.icon}</span>
                    <span className="flex-1">{item.label}</span>
                    {item.planTag && (
                      <span className="text-[9px] font-bold text-scurry-orange bg-scurry-orange-light px-1.5 py-0.5 rounded-md border border-orange-200 whitespace-nowrap">
                        {item.planTag}
                      </span>
                    )}
                  </Link>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Page Header */}
        <div className="bg-white border-b border-gray-200 px-6 sm:px-8 py-5">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">{title}</h1>
          <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
        </div>

        {/* Mobile nav dropdown */}
        <div className="md:hidden px-4 py-3 bg-white border-b border-gray-200">
          <select
            value={location.pathname}
            onChange={(e) => {
              window.location.href = e.target.value
            }}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
          >
            {NAV.flatMap((g) =>
              g.items.filter(canSee).map((item) => (
                <option key={item.id} value={item.path}>
                  {item.icon} {item.label}
                </option>
              ))
            )}
          </select>
        </div>

        {/* Page Content */}
        <div className="flex-1 overflow-y-auto px-6 sm:px-8 py-6">
          <div className="max-w-[860px]">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  )
}

export default SettingsLayout
