# Settings UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current tab-based settings UI with a sidebar-navigated, multi-page settings experience using the new design, while preserving all existing working functionality (API keys, OAuth, email signature, org settings, team management, treasury).

**Architecture:** A new `SettingsLayout` component wraps all `/settings/*` routes, rendering a settings sub-sidebar inside the existing `Layout` content area. Each settings section becomes its own component file. Existing API integrations (React Query mutations, OAuth flows) are preserved and wired into the new UI. New sections without backend support (Billing plans, Affiliate, API Keys management) render as static placeholder UI.

**Tech Stack:** React 18, TypeScript, Tailwind CSS (scurry theme), React Query, React Router, existing shadcn/ui components, Lucide icons.

---

## File Structure

### New files to create:
- `frontend/src/components/settings/SettingsLayout.tsx` — Sub-sidebar + content area wrapper
- `frontend/src/components/settings/SettingsProfile.tsx` — Profile section (personal info, password, sessions)
- `frontend/src/components/settings/SettingsOrganization.tsx` — Org settings + internal domains
- `frontend/src/components/settings/SettingsTeam.tsx` — Team members + invitations
- `frontend/src/components/settings/SettingsBilling.tsx` — Plans, payment, invoices (mostly static)
- `frontend/src/components/settings/SettingsAcorns.tsx` — Acorn allocation + usage + transactions
- `frontend/src/components/settings/SettingsIntegrations.tsx` — API keys + email connection
- `frontend/src/components/settings/SettingsApiKeys.tsx` — External API keys (static placeholder)
- `frontend/src/components/settings/SettingsAffiliate.tsx` — Affiliate program (static placeholder)
- `frontend/src/components/settings/SettingsAuditLog.tsx` — Audit log with filtering

### Files to modify:
- `frontend/src/App.tsx` — Replace individual settings routes with nested `SettingsLayout` routes
- `frontend/src/pages/SettingsPage.tsx` — Gut and redirect, or remove entirely

### Files to delete (absorbed into new components):
- `frontend/src/pages/OrganizationSettingsPage.tsx` — Absorbed into `SettingsOrganization.tsx`
- `frontend/src/pages/TeamSettingsPage.tsx` — Absorbed into `SettingsTeam.tsx`
- `frontend/src/pages/TreasuryPage.tsx` — Absorbed into `SettingsBilling.tsx` + `SettingsAcorns.tsx`

### Files preserved as-is:
- `frontend/src/components/settings/EmailSignatureSettings.tsx` — Reused in integrations section

---

## Task 1: Create SettingsLayout with sub-sidebar

**Files:**
- Create: `frontend/src/components/settings/SettingsLayout.tsx`

This is the shell that all settings pages render inside. It provides a left sub-sidebar with grouped navigation and a scrollable content area on the right. The existing `Layout` component (main app sidebar) wraps this — `SettingsLayout` only manages the settings sub-navigation.

- [ ] **Step 1: Create SettingsLayout.tsx**

```tsx
import React from 'react'
import { Link, useLocation, Outlet } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

const NAV = [
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

        {/* Mobile nav dropdown (visible on small screens) */}
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
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to SettingsLayout (other pre-existing errors are OK)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/SettingsLayout.tsx
git commit -m "feat: add SettingsLayout with sub-sidebar navigation"
```

---

## Task 2: Create SettingsProfile page

**Files:**
- Create: `frontend/src/components/settings/SettingsProfile.tsx`

Port the Profile section from the reference design. Wire up real user data from AuthContext. Password change and sessions are static placeholders (no backend endpoints for these yet).

- [ ] **Step 1: Create SettingsProfile.tsx**

```tsx
import React, { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { authApi } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import EmailSignatureSettings from '@/components/settings/EmailSignatureSettings'

const SettingsProfile: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [saved, setSaved] = useState(false)

  // Password fields
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (user) {
      const parts = (user.full_name || '').split(' ')
      setFirstName(parts[0] || '')
      setLastName(parts.slice(1).join(' ') || '')
      setEmail(user.email || '')
    }
  }, [user])

  const updateProfileMutation = useMutation({
    mutationFn: (data: { full_name: string }) => authApi.updateProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to update profile',
        variant: 'destructive',
      })
    },
  })

  const handleSaveProfile = () => {
    const fullName = [firstName.trim(), lastName.trim()].filter(Boolean).join(' ')
    updateProfileMutation.mutate({ full_name: fullName })
  }

  const togglePassword = (field: string) => {
    setShowPasswords((prev) => ({ ...prev, [field]: !prev[field] }))
  }

  const PasswordInput = ({ field, placeholder, value, onChange }: {
    field: string; placeholder: string; value: string; onChange: (v: string) => void
  }) => (
    <div className="relative">
      <input
        type={showPasswords[field] ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
      />
      <button
        type="button"
        onClick={() => togglePassword(field)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
      >
        {showPasswords[field] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  )

  return (
    <div className="space-y-5">
      {/* Personal Information */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">👤</span> Personal Information
        </div>
        <p className="text-sm text-gray-500 mb-4">Your name, email and company details.</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 mb-3.5">
          <div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">First Name</label>
            <input
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Last Name</label>
            <input
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
          </div>
        </div>

        <div className="mb-3.5">
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Email Address</label>
          <input
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white text-gray-400 cursor-not-allowed"
            value={email}
            disabled
          />
        </div>

        <div className="mb-3.5">
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Company Name</label>
          <input
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white text-gray-400 cursor-not-allowed"
            value={user?.org?.name || ''}
            disabled
          />
        </div>

        <button
          onClick={handleSaveProfile}
          disabled={updateProfileMutation.isPending}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
        >
          {updateProfileMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : saved ? (
            '✓ Saved'
          ) : (
            'Save Changes'
          )}
        </button>
      </div>

      {/* Email Signature - reuse existing component */}
      <EmailSignatureSettings
        initialSignature={user?.email_signature}
        initialEnabled={user?.email_signature_enabled ?? true}
      />

      {/* Change Password */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">🔑</span> Change Password
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Minimum 8 characters with at least one uppercase letter and one number.
        </p>

        <div className="space-y-3.5">
          <div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Current Password</label>
            <PasswordInput field="current" placeholder="••••••••" value={currentPassword} onChange={setCurrentPassword} />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">New Password</label>
            <PasswordInput field="new" placeholder="••••••••" value={newPassword} onChange={setNewPassword} />
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Confirm New Password</label>
            <PasswordInput field="confirm" placeholder="••••••••" value={confirmPassword} onChange={setConfirmPassword} />
          </div>
        </div>

        <button
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors"
          onClick={() =>
            toast({ title: 'Coming Soon', description: 'Password change is not yet available.' })
          }
        >
          Update Password
        </button>
      </div>
    </div>
  )
}

export default SettingsProfile
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsProfile.tsx
git commit -m "feat: add SettingsProfile component with personal info and password sections"
```

---

## Task 3: Create SettingsOrganization page

**Files:**
- Create: `frontend/src/components/settings/SettingsOrganization.tsx`

Port org settings from `OrganizationSettingsPage.tsx` + internal domains from `SettingsPage.tsx`. Wire up real mutations. Add danger zone for owner.

- [ ] **Step 1: Create SettingsOrganization.tsx**

```tsx
import React, { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/components/ui/use-toast'
import { authApi } from '@/lib/api'
import api from '@/lib/api'
import { Loader2 } from 'lucide-react'

const SettingsOrganization: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const role = user?.role || 'member'

  const [orgName, setOrgName] = useState('')
  const [orgDomain, setOrgDomain] = useState('')
  const [internalDomains, setInternalDomains] = useState('')
  const [saved, setSaved] = useState(false)
  const [domainsSaved, setDomainsSaved] = useState(false)

  const { data: currentUser } = useQuery({
    queryKey: ['currentUser'],
    queryFn: async () => {
      const response = await authApi.getMe()
      return response.data
    },
  })

  useEffect(() => {
    if (user?.org) {
      setOrgName(user.org.name || '')
      setOrgDomain(user.org.domain || '')
    }
  }, [user])

  useEffect(() => {
    if (currentUser?.internal_domains) {
      setInternalDomains(currentUser.internal_domains)
    }
  }, [currentUser])

  // Locked state for members
  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          Organization settings are available to Owners and Admins only.
        </div>
      </div>
    )
  }

  const saveOrgMutation = useMutation({
    mutationFn: () => api.put('/auth/organization', { name: orgName, domain: orgDomain }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to update organization',
        variant: 'destructive',
      })
    },
  })

  const updateDomainsMutation = useMutation({
    mutationFn: (domains: string) => authApi.updateSettings(domains),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
      setDomainsSaved(true)
      setTimeout(() => setDomainsSaved(false), 2500)
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to update domains',
        variant: 'destructive',
      })
    },
  })

  return (
    <div className="space-y-5">
      {/* Company Settings */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">🏢</span> Company Settings
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Your organization's identity across the platform.
        </p>

        <div className="mb-3.5">
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Organization Name</label>
          <input
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
          />
        </div>

        <div className="mb-3.5">
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Domain</label>
          <input
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
            value={orgDomain}
            onChange={(e) => setOrgDomain(e.target.value)}
          />
        </div>

        <button
          onClick={() => saveOrgMutation.mutate()}
          disabled={saveOrgMutation.isPending}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
        >
          {saveOrgMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : saved ? (
            '✓ Saved'
          ) : (
            'Save Changes'
          )}
        </button>
      </div>

      {/* Internal Email Domains */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">📧</span> Internal Email Domains
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Specify your company's email domains to filter out internal attendees when looking up deals.
          Only external contacts will be used for automatic deal matching.
        </p>

        <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
          Internal Domains (comma-separated)
        </label>
        <input
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          value={internalDomains}
          onChange={(e) => setInternalDomains(e.target.value)}
        />
        <p className="text-xs text-gray-500 mt-1.5">
          For example: <code className="text-scurry-orange">company.com, subsidiary.io</code>
        </p>

        <div className="mt-3.5 bg-amber-50 border border-amber-200 rounded-lg p-3 flex gap-2.5 text-sm text-amber-800">
          <span>🛈</span>
          <span>
            When a workflow runs, emails from these domains will be excluded from automatic deal
            lookup. This ensures that only client/prospect contacts are used to find the relevant deal.
          </span>
        </div>

        <div className="mt-3.5">
          <button
            onClick={() => updateDomainsMutation.mutate(internalDomains)}
            disabled={updateDomainsMutation.isPending}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
          >
            {updateDomainsMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : domainsSaved ? (
              '✓ Saved'
            ) : (
              'Save Internal Domains'
            )}
          </button>
        </div>
      </div>

      {/* Danger Zone - Owner only */}
      {role === 'owner' && (
        <div className="bg-white border border-red-300 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-red-600 mb-1">
            <span>⚠️</span> Danger Zone
          </div>
          <p className="text-sm text-gray-500 mb-4">
            These actions are permanent and cannot be undone.
          </p>
          <div className="flex items-center justify-between p-4 bg-red-50 rounded-lg border border-red-200">
            <div>
              <div className="font-semibold text-sm">Delete Organization</div>
              <div className="text-xs text-gray-500 mt-0.5">
                Permanently deletes all data, workflows, and sequences.
              </div>
            </div>
            <button className="px-3.5 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors">
              Delete Organization
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default SettingsOrganization
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsOrganization.tsx
git commit -m "feat: add SettingsOrganization with company settings and internal domains"
```

---

## Task 4: Create SettingsTeam page

**Files:**
- Create: `frontend/src/components/settings/SettingsTeam.tsx`

Port from `TeamSettingsPage.tsx` with the new visual design. Preserve real mutations for invite, remove, role change.

- [ ] **Step 1: Create SettingsTeam.tsx**

```tsx
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { teamApi } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/components/ui/use-toast'
import { Loader2 } from 'lucide-react'

const roleBadgeStyles: Record<string, { label: string; classes: string }> = {
  owner: { label: 'Owner', classes: 'text-green-700 bg-green-50' },
  admin: { label: 'Admin', classes: 'text-scurry-orange bg-scurry-orange-light' },
  member: { label: 'Member', classes: 'text-gray-600 bg-gray-100' },
}

const SettingsTeam: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const role = user?.role || 'member'
  const [showModal, setShowModal] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('member')

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          Team management is available to Owners and Admins only.
        </div>
      </div>
    )
  }

  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ['team-members'],
    queryFn: () => teamApi.listMembers().then((r) => r.data),
  })

  const { data: invitations } = useQuery({
    queryKey: ['team-invitations'],
    queryFn: () => teamApi.listInvitations().then((r) => r.data),
  })

  const inviteMutation = useMutation({
    mutationFn: (data: { email: string; role: string }) => teamApi.invite(data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      setInviteEmail('')
      setShowModal(false)
      toast({ title: 'Invitation sent', description: `Invited ${res.data.email} as ${res.data.role}` })
    },
    onError: (err: any) => {
      toast({
        title: 'Error',
        description: err.response?.data?.detail || 'Failed to send invitation',
        variant: 'destructive',
      })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (userId: number) => teamApi.removeMember(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      toast({ title: 'Member removed' })
    },
  })

  const revokeMutation = useMutation({
    mutationFn: (id: number) => teamApi.revokeInvitation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      toast({ title: 'Invitation revoked' })
    },
  })

  const pendingInvitations = invitations?.filter((i: any) => i.status === 'pending') || []
  const getInitials = (name: string) =>
    name
      .split(' ')
      .map((n: string) => n[0])
      .join('')
      .toUpperCase()

  return (
    <div className="space-y-5">
      {/* Team Members */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900">
              <span className="text-scurry-orange">👥</span> Team Members
            </div>
            <p className="text-sm text-gray-500">Manage your team and their access roles.</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors"
          >
            + Invite Member
          </button>
        </div>

        {membersLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-scurry-orange" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  {['Member', 'Email', 'Role', ''].map((h) => (
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
                {members?.map((m: any) => {
                  const badge = roleBadgeStyles[m.role] || roleBadgeStyles.member
                  return (
                    <tr key={m.id}>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-scurry-orange to-scurry-latte flex items-center justify-center text-[11px] text-white font-bold flex-shrink-0">
                            {getInitials(m.full_name || m.email)}
                          </div>
                          <span className="font-semibold">{m.full_name || m.email}</span>
                        </div>
                      </td>
                      <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500">{m.email}</td>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${badge.classes}`}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        {m.role !== 'owner' && m.id !== user?.id && (
                          <button
                            onClick={() => {
                              if (confirm(`Remove ${m.email} from the team?`))
                                removeMutation.mutate(m.id)
                            }}
                            className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors"
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pending Invitations */}
      {pendingInvitations.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">📨</span> Pending Invitations
          </div>
          <p className="text-sm text-gray-500 mb-4">Invitations expire after 7 days.</p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  {['Email', 'Role', ''].map((h) => (
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
                {pendingInvitations.map((inv: any) => (
                  <tr key={inv.id}>
                    <td className="px-2.5 py-3 border-b border-gray-200">{inv.email}</td>
                    <td className="px-2.5 py-3 border-b border-gray-200">
                      <span className="text-[11px] font-bold text-gray-600 bg-gray-100 px-2 py-0.5 rounded-full">
                        {inv.role}
                      </span>
                    </td>
                    <td className="px-2.5 py-3 border-b border-gray-200">
                      <button
                        onClick={() => revokeMutation.mutate(inv.id)}
                        className="px-3.5 py-1.5 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Invite Modal */}
      {showModal && (
        <div
          className="fixed inset-0 bg-black/45 flex items-center justify-center z-50"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-white rounded-xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[17px] font-bold mb-1">Invite a Team Member</div>
            <div className="text-sm text-gray-500 mb-5">
              They'll receive an email invitation valid for 7 days.
            </div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Email Address</label>
            <input
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange mb-3.5"
              placeholder="colleague@company.com"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">Role</label>
            <select
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white cursor-pointer mb-6"
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value)}
            >
              <option value="admin">Admin - can manage billing & team</option>
              <option value="member">Member - product use only</option>
            </select>
            <div className="flex gap-2.5">
              <button
                onClick={() => inviteMutation.mutate({ email: inviteEmail, role: inviteRole })}
                disabled={!inviteEmail || inviteMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
              >
                {inviteMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Send Invitation'}
              </button>
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default SettingsTeam
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsTeam.tsx
git commit -m "feat: add SettingsTeam with member management and invite modal"
```

---

## Task 5: Create SettingsBilling page

**Files:**
- Create: `frontend/src/components/settings/SettingsBilling.tsx`

Mostly static placeholder UI matching the reference design. Wire up real account data from AuthContext where available.

- [ ] **Step 1: Create SettingsBilling.tsx**

```tsx
import React from 'react'
import { useAuth } from '@/contexts/AuthContext'

const plans = [
  { key: 'sapling', name: 'Sapling', price: 99, icon: '🌱' },
  { key: 'oak', name: 'Oak', price: 199, icon: '🌳', popular: true },
  { key: 'redwood', name: 'Redwood', price: 349, icon: '🌲' },
  { key: 'ancient', name: 'Ancient Forest', price: null, icon: '🏔️' },
]

const SettingsBilling: React.FC = () => {
  const { user } = useAuth()
  const role = user?.role || 'member'
  const account = user?.account
  const currentPlan = account?.plan_tier || 'oak'

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          Billing is available to Owners and Admins only.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Current Plan */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">📋</span> Current Plan
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Manage your subscription and upgrade or downgrade at any time.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {plans.map((p) => {
            const isCurrent = p.key === currentPlan
            return (
              <div
                key={p.key}
                className={`relative border-[1.5px] rounded-[10px] p-4 text-center transition-colors ${
                  isCurrent
                    ? 'border-scurry-orange bg-scurry-orange-light'
                    : 'border-gray-200 bg-white'
                }`}
              >
                {p.popular && !isCurrent && (
                  <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-scurry-orange text-white text-[9px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap">
                    MOST POPULAR
                  </div>
                )}
                {isCurrent && (
                  <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-green-600 text-white text-[9px] font-bold px-2.5 py-0.5 rounded-full">
                    CURRENT
                  </div>
                )}
                <div className="text-[22px] mb-1">{p.icon}</div>
                <div className="font-bold text-sm mb-0.5">{p.name}</div>
                <div className="text-xl font-extrabold text-scurry-orange">
                  {p.price ? `$${p.price}` : 'Custom'}
                </div>
                {p.price && <div className="text-[11px] text-gray-500">/user/mo</div>}
                {!isCurrent && (
                  <button className="mt-2.5 w-full py-1.5 px-2.5 bg-white text-gray-900 border border-gray-200 rounded-lg text-[11px] font-medium hover:bg-gray-50 transition-colors">
                    {p.price ? 'Upgrade' : 'Contact Us'}
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Acorn Balance + Payment Method */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Acorn Balance */}
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">🥜</span> Acorn Balance
          </div>
          <div className="text-4xl font-extrabold text-scurry-orange my-1.5">
            {account ? Math.round(account.acorn_balance).toLocaleString() : '—'}
          </div>
          <div className="text-sm text-gray-500 mb-3.5">Acorns remaining — never expire</div>
          <div className="bg-gray-100 rounded-full h-1.5 overflow-hidden mb-2">
            <div className="h-full bg-scurry-orange rounded-full" style={{ width: '71%' }} />
          </div>
          <button className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors">
            Buy More Acorns
          </button>
        </div>

        {/* Payment Method */}
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">💳</span> Payment Method
          </div>
          <div className="flex items-center gap-2.5 p-3 bg-gray-50 rounded-lg border border-gray-200 mb-3.5">
            <div className="w-10 h-6 bg-[#1A1F71] rounded flex items-center justify-center">
              <span className="text-white text-[9px] font-extrabold">VISA</span>
            </div>
            <div>
              <div className="font-semibold text-sm">•••• •••• •••• 4242</div>
              <div className="text-xs text-gray-500">Expires 08/28</div>
            </div>
          </div>
          <button className="px-4 py-2 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors">
            Update Payment Method
          </button>
          <div className="border-t border-gray-200 mt-4 pt-4">
            <div className="text-sm text-gray-500">Next billing</div>
            <div className="font-bold text-[15px] mt-0.5">
              {account?.current_period_ends_at
                ? `${new Date(account.current_period_ends_at).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })} — $199.00`
                : 'No upcoming billing'}
            </div>
          </div>
        </div>
      </div>

      {/* Cancel Subscription */}
      <div className="bg-white border border-red-300 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center justify-between p-4 bg-red-50 rounded-lg">
          <div>
            <div className="font-semibold text-sm">Cancel Subscription</div>
            <div className="text-xs text-gray-500 mt-0.5">
              Access continues until end of billing period.
            </div>
          </div>
          <button className="px-3.5 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors">
            Cancel Plan
          </button>
        </div>
      </div>
    </div>
  )
}

export default SettingsBilling
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsBilling.tsx
git commit -m "feat: add SettingsBilling with plan cards and payment info"
```

---

## Task 6: Create SettingsAcorns page

**Files:**
- Create: `frontend/src/components/settings/SettingsAcorns.tsx`

Wire up real transaction data from `billingApi.getTransactions()` and allocation mode from `teamApi`. Team member usage is static placeholder.

- [ ] **Step 1: Create SettingsAcorns.tsx**

```tsx
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { billingApi, teamApi } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { Loader2 } from 'lucide-react'

const SettingsAcorns: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const role = user?.role || 'member'

  const [threshold, setThreshold] = useState('100')

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          Acorn management is available to Owners and Admins only.
        </div>
      </div>
    )
  }

  const { data: allocationData } = useQuery({
    queryKey: ['acorn-allocation'],
    queryFn: () => teamApi.getAllocationMode().then((r) => r.data),
  })

  const allocationMode = allocationData?.mode || 'shared'

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

  const { data: transactionsData, isLoading: txLoading } = useQuery({
    queryKey: ['acorn-transactions', 1],
    queryFn: () => billingApi.getTransactions(10, 0).then((res) => res.data),
  })

  const transactions = Array.isArray(transactionsData)
    ? transactionsData
    : transactionsData?.transactions ?? []

  const { data: members } = useQuery({
    queryKey: ['team-members'],
    queryFn: () => teamApi.listMembers().then((r) => r.data),
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

      {/* Usage by Team Member */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
          <span className="text-scurry-orange">📊</span> Team Members
        </div>
        <p className="text-sm text-gray-500 mb-4">Current team member list.</p>

        {members?.map((m: any) => (
          <div key={m.id} className="mb-4 last:mb-0">
            <div className="flex justify-between items-center mb-1.5">
              <div className="flex items-center gap-2.5">
                <div className="w-[30px] h-[30px] rounded-full bg-gradient-to-br from-scurry-orange to-scurry-latte flex items-center justify-center text-[11px] text-white font-bold flex-shrink-0">
                  {getInitials(m.full_name || m.email)}
                </div>
                <span className="font-medium text-sm">{m.full_name || m.email}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

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
          <button className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors">
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
                        ? new Date(tx.created_at).toLocaleDateString('en-US', {
                            month: 'short',
                            day: 'numeric',
                          })
                        : '—'}
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
                      {tx.amount ?? 0} 🥜
                    </td>
                    <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500">
                      {tx.description || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-500 text-center py-4">No transactions yet.</p>
        )}
      </div>
    </div>
  )
}

export default SettingsAcorns
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsAcorns.tsx
git commit -m "feat: add SettingsAcorns with allocation mode and transaction history"
```

---

## Task 7: Create SettingsIntegrations page

**Files:**
- Create: `frontend/src/components/settings/SettingsIntegrations.tsx`

This is the most complex page — port all real functionality from current `SettingsPage.tsx`: API key forms (Fireflies, Pipedrive), OAuth email connection (Gmail/Outlook), email signature. Preserve all React Query mutations and OAuth polling logic.

- [ ] **Step 1: Create SettingsIntegrations.tsx**

Copy all the working logic from the current `SettingsPage.tsx` (API key management, OAuth flow, email connection polling) and re-skin it with the new card-based design. Keep the `ApiKeyForm` and `ConnectedAccountCard` components inline since they're only used here.

```tsx
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiKeyApi, ApiKeyInfo, authApi, gmailApiService, outlookApiService } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { useAuth } from '@/contexts/AuthContext'
import {
  Eye,
  EyeOff,
  CheckCircle,
  XCircle,
  Loader2,
  Trash2,
  RefreshCw,
  Plus,
  ExternalLink,
} from 'lucide-react'
import EmailSignatureSettings from '@/components/settings/EmailSignatureSettings'

interface ServiceConfig {
  id: string
  name: string
  icon: string
  description: string
  placeholder: string
  docsUrl?: string
}

const SERVICES: ServiceConfig[] = [
  {
    id: 'fireflies',
    name: 'Fireflies.ai',
    icon: '🎙️',
    description: 'Access meeting transcripts and extract insights from conversations',
    placeholder: 'Enter your Fireflies API key',
    docsUrl: 'https://docs.fireflies.ai/authentication',
  },
  {
    id: 'pipedrive',
    name: 'Pipedrive',
    icon: '🔗',
    description: 'Integrate with your CRM to create and update deals, contacts, and activities',
    placeholder: 'Enter your Pipedrive API key',
    docsUrl: 'https://pipedrive.readme.io/docs/core-api-concepts-authentication',
  },
]

const IntegrationCard: React.FC<{
  service: ServiceConfig
  existingKey?: ApiKeyInfo
  onRefresh: () => void
}> = ({ service, existingKey, onRefresh }) => {
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const saveMutation = useMutation({
    mutationFn: () => apiKeyApi.createOrUpdate(service.id, apiKey),
    onSuccess: () => {
      toast({ title: 'Success', description: `${service.name} API key saved successfully` })
      setApiKey('')
      setTestResult(null)
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
      onRefresh()
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save API key',
        variant: 'destructive',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => apiKeyApi.delete(service.id),
    onSuccess: () => {
      toast({ title: 'Success', description: `${service.name} API key removed` })
      setApiKey('')
      setTestResult(null)
      queryClient.invalidateQueries({ queryKey: ['apiKeys'] })
      onRefresh()
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to remove API key',
        variant: 'destructive',
      })
    },
  })

  const handleTest = async () => {
    if (!apiKey.trim()) return
    setIsTesting(true)
    setTestResult(null)
    try {
      const response = await apiKeyApi.test(service.id, apiKey)
      setTestResult({ success: response.data.success, message: response.data.message })
    } catch (error: any) {
      setTestResult({
        success: false,
        message: error.response?.data?.detail || 'Failed to test API key',
      })
    } finally {
      setIsTesting(false)
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-scurry-orange text-base">{service.icon}</span>
          <span className="font-bold text-[15px]">{service.name}</span>
          {existingKey && (
            <span className="text-[11px] font-bold text-green-700 bg-green-50 px-2 py-0.5 rounded-full">
              Configured
            </span>
          )}
        </div>
        {existingKey && (
          <button
            onClick={() => {
              if (confirm(`Remove your ${service.name} API key?`)) deleteMutation.mutate()
            }}
            className="text-red-600 hover:text-red-700 p-1"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
      <p className="text-sm text-gray-500 mb-1">{service.description}</p>
      {service.docsUrl && (
        <a
          href={service.docsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-scurry-orange hover:underline mb-4 inline-block"
        >
          View API documentation →
        </a>
      )}

      <div className="mb-3.5">
        <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">API Key</label>
        <div className="relative">
          <input
            type={showKey ? 'text' : 'password'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={service.placeholder}
            className="w-full px-3 py-2 pr-9 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          />
          <button
            onClick={() => setShowKey(!showKey)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
          >
            {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {testResult && (
        <div
          className={`flex items-start gap-2 p-3 rounded-lg mb-3.5 text-sm ${
            testResult.success
              ? 'bg-green-50 border border-green-200 text-green-700'
              : 'bg-red-50 border border-red-200 text-red-700'
          }`}
        >
          {testResult.success ? (
            <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          ) : (
            <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          )}
          <span>{testResult.message}</span>
        </div>
      )}

      <div className="flex gap-2.5 mb-3.5">
        <button
          onClick={handleTest}
          disabled={isTesting || !apiKey.trim()}
          className="px-4 py-2 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors inline-flex items-center gap-1.5"
        >
          {isTesting ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Test Connection'}
        </button>
        <button
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending || !apiKey.trim()}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
        >
          {saveMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : existingKey ? (
            'Update API Key'
          ) : (
            'Save API Key'
          )}
        </button>
      </div>

      {existingKey && (
        <div className="text-xs text-gray-400 space-y-1 pt-3 border-t border-gray-200">
          <p>Created: {new Date(existingKey.created_at).toLocaleString()}</p>
          {existingKey.updated_at && (
            <p>Last updated: {new Date(existingKey.updated_at).toLocaleString()}</p>
          )}
          {existingKey.last_used_at && (
            <p>Last used: {new Date(existingKey.last_used_at).toLocaleString()}</p>
          )}
        </div>
      )}
    </div>
  )
}

const SettingsIntegrations: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const role = user?.role || 'member'
  const [isDisconnecting, setIsDisconnecting] = useState(false)
  const [pollingProvider, setPollingProvider] = useState<'gmail' | 'outlook' | null>(null)
  const initialAccountCountRef = useRef<number>(0)
  const pollingTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">Integrations are managed by Owners and Admins.</div>
      </div>
    )
  }

  const { data: apiKeys } = useQuery({
    queryKey: ['apiKeys'],
    queryFn: async () => {
      const response = await apiKeyApi.getAll()
      return response.data
    },
  })

  const { data: currentUser } = useQuery({
    queryKey: ['currentUser'],
    queryFn: async () => {
      const response = await authApi.getMe()
      return response.data
    },
  })

  const {
    data: gmailAccountsData,
    isLoading: isLoadingGmail,
    refetch: refetchGmailAccounts,
  } = useQuery({
    queryKey: ['gmailAccounts'],
    queryFn: async () => {
      try {
        const response = await gmailApiService.getAccounts()
        return response.data
      } catch {
        return { success: false, accounts: [] }
      }
    },
  })

  const gmailAccounts = gmailAccountsData?.accounts || []

  const {
    data: outlookAccountsData,
    isLoading: isLoadingOutlook,
    refetch: refetchOutlookAccounts,
  } = useQuery({
    queryKey: ['outlookAccounts'],
    queryFn: async () => {
      try {
        const response = await outlookApiService.getAccounts()
        return response.data
      } catch {
        return { success: false, accounts: [] }
      }
    },
  })

  const outlookAccounts = outlookAccountsData?.accounts || []

  const connectedGmail = gmailAccounts.length > 0 ? gmailAccounts[0] : null
  const connectedOutlook = outlookAccounts.length > 0 ? outlookAccounts[0] : null
  const hasConnectedAccount = !!connectedGmail || !!connectedOutlook
  const isPolling = pollingProvider !== null

  const stopPolling = useCallback(() => {
    setPollingProvider(null)
    if (pollingTimeoutRef.current) {
      clearTimeout(pollingTimeoutRef.current)
      pollingTimeoutRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!pollingProvider) return
    const refetch = pollingProvider === 'gmail' ? refetchGmailAccounts : refetchOutlookAccounts
    const pollInterval = setInterval(async () => {
      await refetch()
    }, 4000)
    pollingTimeoutRef.current = setTimeout(() => {
      stopPolling()
      toast({
        title: 'Polling stopped',
        description: 'OAuth timeout. Please try connecting again if needed.',
      })
    }, 120000)
    return () => {
      clearInterval(pollInterval)
      if (pollingTimeoutRef.current) clearTimeout(pollingTimeoutRef.current)
    }
  }, [pollingProvider, refetchGmailAccounts, refetchOutlookAccounts, stopPolling, toast])

  const totalAccounts = gmailAccounts.length + outlookAccounts.length
  useEffect(() => {
    if (pollingProvider && totalAccounts > initialAccountCountRef.current) {
      const providerName = pollingProvider === 'gmail' ? 'Gmail' : 'Outlook'
      stopPolling()
      toast({
        title: `${providerName} Connected`,
        description: `New ${providerName} account connected successfully!`,
      })
    }
  }, [totalAccounts, pollingProvider, stopPolling, toast])

  const handleConnect = async (provider: 'gmail' | 'outlook') => {
    const service = provider === 'gmail' ? gmailApiService : outlookApiService
    const providerName = provider === 'gmail' ? 'Gmail' : 'Outlook'
    try {
      const response = await service.getAuthUrl()
      if (response.data.success && response.data.auth_url) {
        initialAccountCountRef.current = gmailAccounts.length + outlookAccounts.length
        window.open(response.data.auth_url, '_blank', 'width=600,height=700')
        setPollingProvider(provider)
        toast({
          title: `${providerName} Authorization`,
          description: 'Complete the authorization in the popup window.',
        })
      }
    } catch (error: any) {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || `Failed to connect ${providerName}`,
        variant: 'destructive',
      })
    }
  }

  const handleDisconnect = async () => {
    const provider = connectedGmail ? 'gmail' : 'outlook'
    const account = connectedGmail || connectedOutlook
    const providerName = provider === 'gmail' ? 'Gmail' : 'Outlook'
    if (!account) return
    if (!confirm(`Disconnect this ${providerName} account?`)) return

    setIsDisconnecting(true)
    try {
      const service = provider === 'gmail' ? gmailApiService : outlookApiService
      await service.disconnect(account.id)
      toast({ title: 'Success', description: `${providerName} account disconnected` })
      queryClient.invalidateQueries({ queryKey: ['gmailAccounts'] })
      queryClient.invalidateQueries({ queryKey: ['outlookAccounts'] })
    } catch (error: any) {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || `Failed to disconnect ${providerName}`,
        variant: 'destructive',
      })
    } finally {
      setIsDisconnecting(false)
    }
  }

  const getExistingKey = (serviceName: string): ApiKeyInfo | undefined => {
    return apiKeys?.find((key) => key.service_name === serviceName)
  }

  return (
    <div className="space-y-5">
      {/* Info banner */}
      <div className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg p-3 flex gap-2">
        <span className="text-scurry-orange">🔑</span>
        <span>
          API keys are stored encrypted and are never shared. Each user has their own set of keys.
          Test your connection before saving to ensure your keys work correctly.
        </span>
      </div>

      {/* Service integrations */}
      {SERVICES.map((service) => (
        <IntegrationCard
          key={service.id}
          service={service}
          existingKey={getExistingKey(service.id)}
          onRefresh={() => {}}
        />
      ))}

      {/* Email Settings */}
      <div className="text-base font-bold mt-2 mb-4">Email Settings</div>

      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-scurry-orange text-base">✉️</span>
          <span className="font-bold text-[15px]">Email Connection</span>
          <button
            onClick={() => {
              refetchGmailAccounts()
              refetchOutlookAccounts()
            }}
            className="text-gray-500 hover:text-gray-700"
          >
            <RefreshCw
              className={`w-4 h-4 ${isLoadingGmail || isLoadingOutlook ? 'animate-spin' : ''}`}
            />
          </button>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Connect your email account to send emails directly through the workflow platform. You can
          connect one Gmail or Outlook account.
        </p>

        {hasConnectedAccount ? (
          <div className="flex items-center gap-2.5 p-3 bg-green-50 border border-green-200 rounded-lg mb-3.5 text-sm text-green-700 font-semibold">
            ✓ Connected: {connectedGmail ? 'Gmail' : 'Outlook'} —{' '}
            {connectedGmail?.email || connectedOutlook?.email}
            <button
              onClick={handleDisconnect}
              disabled={isDisconnecting}
              className="ml-auto px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors inline-flex items-center gap-1"
            >
              {isDisconnecting ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Disconnect'}
            </button>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2.5 p-3 bg-gray-50 border border-gray-200 rounded-lg mb-3.5 text-sm text-gray-500">
              ✉️ No email account connected. Connect a Gmail or Outlook account to start sending
              emails.
            </div>
            <div className="flex gap-2.5 mb-3.5">
              {isPolling ? (
                <>
                  <button
                    disabled
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-gray-400 text-white text-sm font-semibold rounded-lg"
                  >
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Waiting for {pollingProvider === 'gmail' ? 'Gmail' : 'Outlook'}{' '}
                    authorization...
                  </button>
                  <button
                    onClick={stopPolling}
                    className="px-4 py-2 bg-white text-gray-500 border border-gray-200 rounded-lg text-sm hover:text-gray-900 transition-colors"
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => handleConnect('gmail')}
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Connect Gmail
                    <ExternalLink className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleConnect('outlook')}
                    className="inline-flex items-center gap-1.5 px-4 py-2 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Connect Outlook
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </>
              )}
            </div>
          </>
        )}

        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex gap-2.5 text-sm text-amber-800">
          <span>✅</span>
          <div>
            <div className="font-semibold mb-1">Benefits of connecting your email:</div>
            <ul className="list-disc pl-5 space-y-0.5">
              <li>Emails sent directly from your own address</li>
              <li>Open and click tracking included</li>
              <li>Full HTML email support</li>
              <li>CC/BCC recipient support</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Email Signature */}
      <EmailSignatureSettings
        initialSignature={currentUser?.email_signature}
        initialEnabled={currentUser?.email_signature_enabled ?? true}
      />
    </div>
  )
}

export default SettingsIntegrations
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/settings/SettingsIntegrations.tsx
git commit -m "feat: add SettingsIntegrations with API keys, email OAuth, and signature"
```

---

## Task 8: Create SettingsApiKeys, SettingsAffiliate, SettingsAuditLog pages

**Files:**
- Create: `frontend/src/components/settings/SettingsApiKeys.tsx`
- Create: `frontend/src/components/settings/SettingsAffiliate.tsx`
- Create: `frontend/src/components/settings/SettingsAuditLog.tsx`

These are the remaining pages. API Keys and Affiliate are static placeholders. Audit Log wires up the real `teamApi.getAuditLog()` endpoint.

- [ ] **Step 1: Create SettingsApiKeys.tsx**

```tsx
import React from 'react'
import { useAuth } from '@/contexts/AuthContext'

const SettingsApiKeys: React.FC = () => {
  const { user } = useAuth()
  const role = user?.role || 'member'
  const plan = user?.account?.plan_tier || 'oak'

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          API Keys are available to Owners and Admins on Redwood plan and above.
        </div>
      </div>
    )
  }

  if (plan === 'sapling' || plan === 'oak') {
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
```

- [ ] **Step 2: Create SettingsAffiliate.tsx**

```tsx
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
```

- [ ] **Step 3: Create SettingsAuditLog.tsx**

```tsx
import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { teamApi } from '@/lib/api'
import { Loader2 } from 'lucide-react'

const actionBadgeStyles: Record<string, string> = {
  billing: 'text-scurry-orange bg-scurry-orange-light',
  integration: 'text-gray-600 bg-gray-100',
  team: 'text-scurry-orange bg-scurry-orange-light',
  login: 'text-green-700 bg-green-50',
  workflow: 'text-gray-600 bg-gray-100',
  settings: 'text-gray-600 bg-gray-100',
}

const FILTERS = ['all', 'login', 'billing', 'team', 'integration', 'workflow', 'settings']

const SettingsAuditLog: React.FC = () => {
  const { user } = useAuth()
  const role = user?.role || 'member'
  const [filter, setFilter] = useState('all')

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">🔒</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">Access Restricted</div>
        <div className="text-sm text-gray-500">
          Audit log is available to Owners and Admins only.
        </div>
      </div>
    )
  }

  const { data: auditData, isLoading } = useQuery({
    queryKey: ['audit-log', filter],
    queryFn: () =>
      teamApi
        .getAuditLog({
          action: filter === 'all' ? undefined : filter,
          limit: 50,
        })
        .then((r) => r.data),
  })

  const logs = Array.isArray(auditData) ? auditData : auditData?.entries ?? []

  return (
    <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
      <div className="flex items-start justify-between mb-4 flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900">
            <span className="text-scurry-orange">📋</span> Audit Log
          </div>
          <p className="text-sm text-gray-500">All significant account events.</p>
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-lg text-[11px] font-bold capitalize border transition-colors ${
                filter === f
                  ? 'bg-scurry-orange text-white border-scurry-orange'
                  : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-scurry-orange" />
        </div>
      ) : logs.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                {['Timestamp', 'User', 'Type', 'Description'].map((h) => (
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
              {logs.map((l: any, i: number) => (
                <tr key={l.id || i}>
                  <td className="px-2.5 py-3 border-b border-gray-200 font-mono text-[11px] text-gray-500 whitespace-nowrap">
                    {l.created_at
                      ? new Date(l.created_at).toLocaleString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : l.date || '—'}
                  </td>
                  <td className="px-2.5 py-3 border-b border-gray-200 font-medium">
                    {l.user_name || l.user || '—'}
                  </td>
                  <td className="px-2.5 py-3 border-b border-gray-200">
                    <span
                      className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                        actionBadgeStyles[l.action] || 'text-gray-600 bg-gray-100'
                      }`}
                    >
                      {l.action || '—'}
                    </span>
                  </td>
                  <td className="px-2.5 py-3 border-b border-gray-200 text-gray-500">
                    {l.description || l.desc || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-gray-500 text-center py-8">No audit events found.</p>
      )}
    </div>
  )
}

export default SettingsAuditLog
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/SettingsApiKeys.tsx frontend/src/components/settings/SettingsAffiliate.tsx frontend/src/components/settings/SettingsAuditLog.tsx
git commit -m "feat: add SettingsApiKeys, SettingsAffiliate, and SettingsAuditLog pages"
```

---

## Task 9: Update App.tsx routing and remove old pages

**Files:**
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/pages/OrganizationSettingsPage.tsx`
- Delete: `frontend/src/pages/TeamSettingsPage.tsx`
- Delete: `frontend/src/pages/TreasuryPage.tsx`

Replace individual settings routes with a nested `SettingsLayout` using `<Outlet>`. Old settings page files are no longer needed.

- [ ] **Step 1: Update App.tsx**

Replace the imports for old settings pages and routes with the new structure. The key change is using React Router nested routes with `SettingsLayout` as the parent element.

Replace the existing settings-related imports at the top of `App.tsx`:

```tsx
// Remove these imports:
// import SettingsPage from '@/pages/SettingsPage'
// import TreasuryPage from '@/pages/TreasuryPage'
// import OrganizationSettingsPage from '@/pages/OrganizationSettingsPage'
// import TeamSettingsPage from '@/pages/TeamSettingsPage'

// Add these imports:
import SettingsLayout from '@/components/settings/SettingsLayout'
import SettingsProfile from '@/components/settings/SettingsProfile'
import SettingsOrganization from '@/components/settings/SettingsOrganization'
import SettingsTeam from '@/components/settings/SettingsTeam'
import SettingsBilling from '@/components/settings/SettingsBilling'
import SettingsAcorns from '@/components/settings/SettingsAcorns'
import SettingsIntegrations from '@/components/settings/SettingsIntegrations'
import SettingsApiKeys from '@/components/settings/SettingsApiKeys'
import SettingsAffiliate from '@/components/settings/SettingsAffiliate'
import SettingsAuditLog from '@/components/settings/SettingsAuditLog'
```

Replace the four existing settings `<Route>` blocks (for `/settings`, `/settings/treasury`, `/settings/organization`, `/settings/team`) with a single nested route:

```tsx
<Route
  path="/settings"
  element={
    <ProtectedRoute>
      <Layout>
        <SettingsLayout />
      </Layout>
    </ProtectedRoute>
  }
>
  <Route index element={<SettingsProfile />} />
  <Route path="organization" element={<SettingsOrganization />} />
  <Route path="team" element={<SettingsTeam />} />
  <Route path="billing" element={<SettingsBilling />} />
  <Route path="acorns" element={<SettingsAcorns />} />
  <Route path="integrations" element={<SettingsIntegrations />} />
  <Route path="api-keys" element={<SettingsApiKeys />} />
  <Route path="affiliate" element={<SettingsAffiliate />} />
  <Route path="audit-log" element={<SettingsAuditLog />} />
</Route>
```

- [ ] **Step 2: Delete old page files**

```bash
rm frontend/src/pages/OrganizationSettingsPage.tsx
rm frontend/src/pages/TeamSettingsPage.tsx
rm frontend/src/pages/TreasuryPage.tsx
```

- [ ] **Step 3: Check if SettingsPage.tsx is imported anywhere else**

Search for imports of `SettingsPage` across the codebase. If only `App.tsx` imports it, delete it too. If other files reference it, leave it as a redirect.

```bash
cd /home/tauhid/code/aibot2/frontend && grep -r "SettingsPage" src/ --include="*.tsx" --include="*.ts" -l
```

If only `App.tsx` references it:

```bash
rm frontend/src/pages/SettingsPage.tsx
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /home/tauhid/code/aibot2/frontend && npx tsc --noEmit
```

Fix any import errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: replace old settings pages with new sidebar-navigated settings layout"
```

---

## Task 10: Check for updateProfile API method

**Files:**
- Possibly modify: `frontend/src/lib/api.ts`

The `SettingsProfile` component calls `authApi.updateProfile()`. Verify this method exists in `api.ts`. If not, add it.

- [ ] **Step 1: Check if authApi.updateProfile exists**

```bash
cd /home/tauhid/code/aibot2/frontend && grep -n "updateProfile" src/lib/api.ts
```

- [ ] **Step 2: If missing, add it to the authApi object**

Add to the `authApi` object in `src/lib/api.ts`:

```typescript
updateProfile: (data: { full_name: string }) => api.put('/auth/profile', data),
```

- [ ] **Step 3: Check backend has the endpoint**

```bash
cd /home/tauhid/code/aibot2/backend && grep -n "profile" auth.py
```

If the backend doesn't have a `PUT /auth/profile` endpoint, the Profile save button will show a toast error gracefully. Add a comment noting this is a placeholder.

- [ ] **Step 4: Commit if changes were made**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add updateProfile method to authApi"
```

---

## Task 11: Visual verification and final fixes

- [ ] **Step 1: Start the frontend dev server**

```bash
cd /home/tauhid/code/aibot2/frontend && pnpm run dev
```

- [ ] **Step 2: Navigate to /settings and verify**

Open `http://localhost:3000/settings` in a browser. Check:
- Sub-sidebar renders with all navigation groups
- Clicking each nav item routes to the correct section
- Profile page shows user data from AuthContext
- Organization page shows org name/domain with real data
- Team page shows real team members from the API
- Integrations page shows API key forms and email connection
- Mobile: on small screens, the sidebar collapses to a dropdown

- [ ] **Step 3: Fix any visual issues**

Common issues to check:
- Sidebar overlapping or not aligned with the main Layout sidebar
- Content area not scrolling properly
- Mobile responsiveness

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "fix: polish settings UI layout and fix visual issues"
```
