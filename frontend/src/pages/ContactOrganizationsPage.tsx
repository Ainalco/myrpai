/**
 * ContactOrganizationsPage.tsx
 * ============================
 * Contacts > Organizations — wired to backend via useQuery.
 */
import React, { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  Search,
  ChevronRight,
  ExternalLink,
} from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { contactOrgsApi, type OrgDetail as OrgDetailType } from '@/lib/api'

// ─── LOOKUPS ────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-scurry-green-light text-scurry-green',
  paused: 'bg-yellow-100 text-yellow-700',
  do_not_contact: 'bg-scurry-red-light text-scurry-red',
  bounced: 'bg-scurry-red-light text-scurry-red',
}
const STATUS_LABELS: Record<string, string> = {
  active: 'Active', paused: 'Paused', do_not_contact: 'DNC', bounced: 'Bounced',
}

// ─── ORG DETAIL ─────────────────────────────────────────────────────────

function OrgDetail({ org, onBack }: { org: OrgDetailType; onBack: () => void }) {
  const contacts = org.persons || []

  return (
    <div>
      <button
        onClick={onBack}
        className="group flex items-center gap-1.5 text-scurry-latte text-sm font-medium mb-5 bg-transparent border-none cursor-pointer hover:text-scurry-orange transition-colors"
      >
        <ArrowLeft className="h-4 w-4 group-hover:-translate-x-0.5 transition-transform" />
        Back to organizations
      </button>

      {/* Header card */}
      <div className="bg-white rounded-xl border border-scurry-gray-border p-5 mb-5">
        <div className="flex items-center gap-4">
          <div className={`w-[52px] h-[52px] rounded-xl flex items-center justify-center text-xl font-bold ${org.dnc ? 'bg-scurry-red-light text-scurry-red' : 'bg-scurry-blue-bg text-scurry-blue-text'}`}>
            {org.name.substring(0, 2).toUpperCase()}
          </div>
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-bold text-scurry-espresso">{org.name}</h1>
              {org.dnc && (
                <span className="inline-flex items-center text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-scurry-red-light text-scurry-red">
                  Do Not Contact
                </span>
              )}
            </div>
            <div className="text-sm text-scurry-latte mt-1">
              {org.domain || '—'} · {org.contacts} {org.contacts === 1 ? 'person' : 'persons'} · DNC propagation: {org.dncProp ? 'ON' : 'OFF'}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3 mt-5 pt-5 border-t border-scurry-gray-border">
          <div className="text-center py-1">
            <div className="text-2xl font-bold text-scurry-espresso">{org.contacts}</div>
            <div className="text-xs text-scurry-latte mt-0.5">Persons</div>
          </div>
          <div className="text-center py-1">
            <div className="text-2xl font-bold text-scurry-blue-text">{org.openDeals}</div>
            <div className="text-xs text-scurry-latte mt-0.5">Open Deals</div>
          </div>
          <div className="text-center py-1">
            <div className="text-2xl font-bold text-scurry-orange">${(org.totalValue / 1000).toFixed(0)}K</div>
            <div className="text-xs text-scurry-latte mt-0.5">Pipeline</div>
          </div>
          <div className="text-center py-1">
            <div className={`text-2xl font-bold ${org.dnc ? 'text-scurry-red' : 'text-scurry-green'}`}>{org.dnc ? 'DNC' : 'Active'}</div>
            <div className="text-xs text-scurry-latte mt-0.5">Status</div>
          </div>
        </div>
      </div>

      {/* Persons at org */}
      <h3 className="text-base font-bold text-scurry-espresso mb-3">Persons at {org.name}</h3>
      <div className="bg-white rounded-xl border border-scurry-gray-border overflow-hidden">
        {contacts.length === 0 ? (
          <p className="text-sm text-scurry-latte text-center py-8">No persons linked to this organization.</p>
        ) : contacts.map((c, i) => (
          <div key={c.id} className={`flex items-center gap-3 px-5 py-3 ${i < contacts.length - 1 ? 'border-b border-scurry-gray-border' : ''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${STATUS_STYLES[c.status] || 'bg-gray-100 text-gray-500'}`}>
              {(c.name || c.email).split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()}
            </div>
            <div className="flex-1">
              <span className="font-semibold text-sm text-scurry-espresso">{c.name || c.email}</span>
              <span className="text-xs text-scurry-latte ml-2">{c.email}</span>
            </div>
            <span className={`inline-flex items-center text-[11px] font-bold px-2.5 py-0.5 rounded-full ${STATUS_STYLES[c.status] || 'bg-gray-100 text-gray-500'}`}>
              {STATUS_LABELS[c.status] || c.status}
            </span>
          </div>
        ))}
      </div>

      {/* View in Pipedrive */}
      <div className="mt-4">
        <Button
          size="sm"
          className="bg-scurry-orange hover:bg-scurry-orange-hover text-white"
          onClick={() => window.open('https://app.pipedrive.com', '_blank')}
        >
          <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
          View in Pipedrive
        </Button>
      </div>
    </div>
  )
}

// ─── MAIN PAGE ──────────────────────────────────────────────────────────

const ContactOrganizationsPage: React.FC = () => {
  const [selectedOrgId, setSelectedOrgId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const { data: orgsResponse } = useQuery({
    queryKey: ['contact-organizations', search],
    queryFn: () => contactOrgsApi.list({ search: search || undefined }).then(r => r.data),
  })
  const orgs = orgsResponse?.items ?? []

  const { data: selectedOrgDetail } = useQuery({
    queryKey: ['contact-org-detail', selectedOrgId],
    queryFn: () => contactOrgsApi.getById(selectedOrgId!).then(r => r.data),
    enabled: !!selectedOrgId,
  })

  const filtered = useMemo(
    () => orgs.filter(o => !search || o.name.toLowerCase().includes(search.toLowerCase()) || (o.domain || '').includes(search.toLowerCase())),
    [orgs, search]
  )

  if (selectedOrgId && selectedOrgDetail) {
    return <OrgDetail org={selectedOrgDetail} onBack={() => setSelectedOrgId(null)} />
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-scurry-espresso">Organizations</h1>
        <p className="text-sm text-scurry-latte mt-1">Companies and their associated contacts</p>
      </div>

      {/* Search */}
      <div className="mb-5">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-scurry-gray-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search organizations..."
            className="pl-9 border-scurry-gray-border focus:border-scurry-orange focus:ring-scurry-orange/10"
          />
        </div>
      </div>

      {/* Org list */}
      <div className="bg-white rounded-xl border border-scurry-gray-border overflow-hidden">
        {filtered.length === 0 ? (
          <div className="py-12 text-center text-sm text-scurry-latte">No organizations found</div>
        ) : filtered.map((o, i) => (
          <div
            key={o.id}
            onClick={() => setSelectedOrgId(o.id)}
            className={`flex items-center gap-4 px-5 py-3.5 cursor-pointer transition-colors hover:bg-scurry-foam/50 ${
              i < filtered.length - 1 ? 'border-b border-scurry-gray-border' : ''
            }`}
          >
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-sm font-bold shrink-0 ${o.dnc ? 'bg-scurry-red-light text-scurry-red' : 'bg-scurry-blue-bg text-scurry-blue-text'}`}>
              {o.name.substring(0, 2).toUpperCase()}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-scurry-espresso">{o.name}</span>
                {o.dnc && (
                  <span className="inline-flex items-center text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-scurry-red-light text-scurry-red">DNC</span>
                )}
              </div>
              <div className="text-sm text-scurry-latte mt-0.5">{o.domain || '—'} · {o.contacts} {o.contacts === 1 ? 'person' : 'persons'}</div>
            </div>
            <div className="text-right">
              <div className="text-sm font-medium text-scurry-espresso">{o.openDeals} open deals</div>
              <div className="text-xs text-scurry-gray-muted">${(o.totalValue / 1000).toFixed(0)}K pipeline</div>
            </div>
            <ChevronRight className="h-4 w-4 text-scurry-gray-border" />
          </div>
        ))}
      </div>
    </div>
  )
}

export default ContactOrganizationsPage
