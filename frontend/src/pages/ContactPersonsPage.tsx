/**
 * ContactPersonsPage.tsx
 * ======================
 * Contacts > Persons — wired to backend via useQuery.
 */
import React, { useState, useMemo } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import {
  ArrowLeft,
  Search,
  Download,
  ChevronRight,
  ChevronDown,
  ExternalLink,
  Activity,
  User,
  Building2,
  RefreshCw,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { contactsApi, type ContactListItem, type ContactDetail as ContactDetailType, type ThreadMessage } from '@/lib/api'

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
const SENTIMENT_STYLES: Record<string, string> = {
  positive: 'bg-scurry-green-light text-scurry-green',
  neutral: 'bg-yellow-100 text-yellow-700',
  negative: 'bg-scurry-red-light text-scurry-red',
  unknown: 'bg-gray-100 text-scurry-gray-muted',
}
const ENGAGEMENT_STYLES: Record<string, string> = {
  high: 'bg-scurry-green-light text-scurry-green',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-scurry-red-light text-scurry-red',
}
const DIR_STYLES: Record<string, string> = {
  inbound: 'bg-scurry-green-light text-scurry-green',
  outbound: 'bg-scurry-blue-bg text-scurry-blue-text',
  internal: 'bg-gray-100 text-scurry-gray-muted',
}
const THREAD_STATUS_LABELS: Record<string, string> = {
  active: 'Active', resolved: 'Resolved', waiting_on_them: 'Waiting on them', waiting_on_us: 'Waiting on us',
}
const ACTIVITY_ICONS: Record<string, string> = {
  email_sent: '📤', email_reply: '📩', email_bounced: '⚠️', meeting: '🎯',
  note: '📝', deal_stage_change: '📊', deal_status_change: '🏁',
  sequence_started: '🚀', sequence_paused: '⏸️', status_change: '🔄',
}

// ─── STATUS BADGE ───────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center text-[11px] font-bold px-2.5 py-0.5 rounded-full ${STATUS_STYLES[status] || 'bg-gray-100 text-gray-500'}`}>
      {STATUS_LABELS[status] || status}
    </span>
  )
}

function StyledBadge({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center text-[11px] font-bold px-2.5 py-0.5 rounded-full ${className}`}>
      {children}
    </span>
  )
}

// ─── STAT ───────────────────────────────────────────────────────────────

function Stat({ label, value, className }: { label: string; value: string | number; className?: string }) {
  return (
    <div className="text-center py-1">
      <div className={`text-2xl font-bold ${className || 'text-scurry-espresso'}`}>{value}</div>
      <div className="text-xs text-scurry-latte mt-0.5">{label}</div>
    </div>
  )
}

// ─── COLLAPSIBLE TEXT ───────────────────────────────────────────────────

const COLLAPSE_THRESHOLD = 120 // characters

function CollapsibleText({ text, className }: { text: string | null; className?: string }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return null
  const isLong = text.length > COLLAPSE_THRESHOLD
  return (
    <div className={className}>
      <span className={`whitespace-pre-line ${!expanded && isLong ? 'line-clamp-3' : ''}`}>{text}</span>
      {isLong && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
          className="text-scurry-orange text-xs font-semibold mt-1 bg-transparent border-none cursor-pointer hover:underline block"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}

// ─── EMAIL MESSAGE ──────────────────────────────────────────────────────

function EmailMessage({ msg }: { msg: ThreadMessage }) {
  const isYou = msg.from === 'you'
  return (
    <div className={`flex ${isYou ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[85%] rounded-xl px-4 py-3 ${isYou ? 'bg-scurry-orange-light border border-scurry-orange/10' : 'bg-white border border-scurry-gray-border'}`}>
        <div className="flex items-center gap-2 mb-1">
          <span className={`text-xs font-bold ${isYou ? 'text-scurry-orange' : 'text-scurry-espresso'}`}>{isYou ? 'You' : msg.from}</span>
          <span className="text-[11px] text-scurry-gray-muted">{msg.at}</span>
        </div>
        {msg.subject && <div className="text-xs font-semibold text-scurry-espresso mb-1">{msg.subject}</div>}
        <div className="text-[13px] text-scurry-espresso leading-relaxed whitespace-pre-line">{msg.body}</div>
      </div>
    </div>
  )
}

// ─── CONTACT DETAIL ─────────────────────────────────────────────────────

function ContactDetail({ contact: c, onBack }: { contact: ContactDetailType; onBack: () => void }) {
  const [tab, setTab] = useState('pulse')
  const [expandedThread, setExpandedThread] = useState<string | null>(null)
  const [expandedDeal, setExpandedDeal] = useState<number | null>(null)
  const p = c.pulse

  const tabs = [
    { key: 'pulse', label: 'Pulse' },
    { key: 'timeline', label: 'Timeline', count: c.timeline.length },
    { key: 'deals', label: 'Deals', count: c.deals.length },
    { key: 'threads', label: 'Threads', count: c.threads.length },
    { key: 'meetings', label: 'Meetings', count: c.meetings.length },
  ]

  return (
    <div>
      {/* Back */}
      <button onClick={onBack} className="group flex items-center gap-1.5 text-scurry-latte text-sm font-medium mb-5 bg-transparent border-none cursor-pointer hover:text-scurry-orange transition-colors">
        <ArrowLeft className="h-4 w-4 group-hover:-translate-x-0.5 transition-transform" />
        Back to persons
      </button>

      {/* Header card */}
      <div className="bg-white rounded-xl border border-scurry-gray-border p-5 mb-5">
        <div className="flex items-start gap-4">
          <div className="w-[52px] h-[52px] rounded-full bg-scurry-orange flex items-center justify-center text-xl font-bold text-white shrink-0">
            {(c.name || c.email).split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-bold text-scurry-espresso">{c.name || c.email}</h1>
              <StatusBadge status={c.status} />
              <StyledBadge className={SENTIMENT_STYLES[p.sentiment ?? ''] || ''}>{p.sentiment}</StyledBadge>
              <StyledBadge className={ENGAGEMENT_STYLES[p.engagement ?? ''] || ''}>{p.engagement} engagement</StyledBadge>
            </div>
            <div className="text-sm text-scurry-latte mt-1.5">
              {c.emails.join(' · ')} · {c.orgName}
              {c.pipedrive && <span className="text-[11px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-px rounded ml-2">PIPEDRIVE</span>}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-7 gap-2 mt-5 pt-5 border-t border-scurry-gray-border">
          <Stat label="Sent" value={c.stats.sent} />
          <Stat label="Received" value={c.stats.received} />
          <Stat label="Reply Rate" value={c.stats.rate} className="text-scurry-green" />
          <Stat label="Meetings" value={c.stats.meetings} />
          <Stat label="Sequences" value={c.stats.sequences} />
          <Stat label="Open Deals" value={c.stats.openDeals} className="text-scurry-blue-text" />
          <Stat label="Value" value={`$${(c.stats.dealValue / 1000).toFixed(0)}K`} className="text-scurry-orange" />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-scurry-gray-border pb-3 mb-5">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-1.5 rounded-full text-sm font-semibold border-none cursor-pointer transition-all ${
              tab === t.key
                ? 'bg-scurry-orange text-white'
                : 'bg-transparent text-scurry-latte hover:bg-scurry-foam'
            }`}
          >
            {t.label}{t.count !== undefined ? ` (${t.count})` : ''}
          </button>
        ))}
      </div>

      {/* PULSE */}
      {tab === 'pulse' && (
        <div className="flex flex-col gap-4">
          <div className="bg-scurry-foam border border-scurry-energy-burst/20 rounded-xl p-3.5 text-sm text-scurry-latte flex items-center gap-2">
            🧠 AI-powered contact intelligence — updated from your latest interactions
          </div>
          <div className="bg-white rounded-xl border border-scurry-gray-border p-5">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="h-[18px] w-[18px] text-scurry-orange" />
              <h3 className="text-base font-bold text-scurry-espresso">Contact Pulse</h3>
              <span className="text-[11px] text-scurry-gray-muted ml-auto">Updated 2h ago</span>
            </div>
            <p className="text-sm leading-7 text-scurry-espresso">{p.summary}</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white rounded-xl border border-scurry-gray-border p-5">
              <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-2.5">Key Topics</div>
              <div className="flex flex-wrap gap-1.5">
                {p.topics.map(t => <StyledBadge key={t} className="bg-scurry-blue-bg text-scurry-blue-text">{t}</StyledBadge>)}
              </div>
            </div>
            <div className="bg-white rounded-xl border border-scurry-gray-border p-5">
              <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-2.5">Objections</div>
              <div className="flex flex-wrap gap-1.5">
                {p.objections.length ? p.objections.map(o => <StyledBadge key={o} className="bg-scurry-red-light text-scurry-red">{o}</StyledBadge>) : <span className="text-sm text-scurry-gray-muted">None raised</span>}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              ['Intent', p.intent, 'text-scurry-espresso'],
              ['Recommended', p.action, 'text-scurry-green'],
              ['Last Meeting', p.lastMeeting || 'None', 'text-scurry-espresso'],
            ].map(([l, v, cls]) => (
              <div key={l as string} className="bg-white rounded-xl border border-scurry-gray-border p-5 text-center">
                <div className="text-[11px] text-scurry-latte uppercase tracking-wider">{l}</div>
                <div className={`text-base font-bold mt-1.5 capitalize ${cls}`}>{String(v).replace(/_/g, ' ')}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TIMELINE */}
      {tab === 'timeline' && (
        <div className="bg-white rounded-xl border border-scurry-gray-border p-5">
          {c.timeline.length === 0 ? (
            <p className="text-sm text-scurry-latte text-center py-10">No activity yet.</p>
          ) : (
            <div className="relative pl-8">
              <div className="absolute left-[11px] top-1 bottom-1 w-0.5 bg-scurry-gray-border" />
              {c.timeline.map((a, i) => (
                <div key={a.id} className={`relative ${i < c.timeline.length - 1 ? 'pb-6' : ''}`}>
                  <div className={`absolute -left-[26px] top-0.5 w-[22px] h-[22px] rounded-full flex items-center justify-center text-[11px] ${a.dir === 'inbound' ? 'bg-scurry-green-light' : a.dir === 'outbound' ? 'bg-scurry-blue-bg' : 'bg-scurry-gray-light'}`}>
                    {ACTIVITY_ICONS[a.type] || '•'}
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-semibold text-scurry-espresso capitalize">{a.type.replace(/_/g, ' ')}</span>
                      <StyledBadge className={DIR_STYLES[a.dir ?? ''] || ''}>{a.dir}</StyledBadge>
                      {a.deal && <StyledBadge className="bg-purple-50 text-purple-700">{a.deal}</StyledBadge>}
                    </div>
                    {a.subject && <div className="text-sm font-medium text-scurry-espresso mt-1">{a.subject}</div>}
                    <CollapsibleText text={a.summary} className="text-sm text-scurry-latte mt-0.5 leading-relaxed" />
                    <div className="text-[11px] text-scurry-gray-muted mt-1">{a.at} · {(a.source ?? '').replace(/_/g, ' ')}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* DEALS */}
      {tab === 'deals' && (
        <div className="flex flex-col gap-3">
          {c.deals.length === 0 ? (
            <div className="bg-white rounded-xl border border-scurry-gray-border p-5">
              <p className="text-sm text-scurry-latte text-center py-5">No deals.</p>
            </div>
          ) : c.deals.map(d => {
            const isOpen = expandedDeal === d.id
            const dealActivity = c.timeline.filter(a => a.deal && d.title.includes(a.deal))
            return (
              <div key={d.id} className="bg-white rounded-xl border border-scurry-gray-border overflow-hidden">
                <div className="p-5 cursor-pointer hover:bg-scurry-foam/50 transition-colors" onClick={() => setExpandedDeal(isOpen ? null : d.id)}>
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-scurry-espresso">{d.title}</span>
                        <StyledBadge className={d.status === 'open' ? 'bg-scurry-green-light text-scurry-green' : d.status === 'won' ? 'bg-scurry-blue-bg text-scurry-blue-text' : 'bg-scurry-red-light text-scurry-red'}>{d.status}</StyledBadge>
                      </div>
                      <div className="text-sm text-scurry-latte mt-1">Stage: {d.stage} · Close: {d.expected}</div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-2xl font-bold text-scurry-espresso">${((d.value ?? 0) / 1000).toFixed(0)}K</span>
                      <ChevronDown className={`h-4 w-4 text-scurry-gray-muted transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                    </div>
                  </div>
                </div>
                {isOpen && (
                  <div className="border-t border-scurry-gray-border bg-scurry-gray-light">
                    <div className="px-5 pt-4 pb-3 flex gap-6">
                      <div><div className="text-[11px] text-scurry-gray-muted uppercase tracking-wider">Created</div><div className="text-sm font-semibold text-scurry-espresso mt-0.5">Feb 15, 2026</div></div>
                      <div><div className="text-[11px] text-scurry-gray-muted uppercase tracking-wider">Probability</div><div className="text-sm font-semibold text-scurry-espresso mt-0.5">{d.status === 'won' ? '100%' : d.stage === 'Negotiation' ? '70%' : d.stage === 'Proposal' ? '40%' : '20%'}</div></div>
                      <div><div className="text-[11px] text-scurry-gray-muted uppercase tracking-wider">Owner</div><div className="text-sm font-semibold text-scurry-espresso mt-0.5">Joshua</div></div>
                      <div><div className="text-[11px] text-scurry-gray-muted uppercase tracking-wider">Activities</div><div className="text-sm font-semibold text-scurry-espresso mt-0.5">{dealActivity.length}</div></div>
                    </div>
                    {dealActivity.length > 0 && (
                      <div className="px-5 pb-3">
                        <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-2">Recent Activity</div>
                        {dealActivity.slice(0, 4).map(a => (
                          <div key={a.id} className="flex items-start gap-2.5 py-1.5">
                            <span className="text-sm mt-px">{ACTIVITY_ICONS[a.type] || '•'}</span>
                            <div className="flex-1">
                              <span className="text-sm font-medium text-scurry-espresso capitalize">{a.type.replace(/_/g, ' ')}</span>
                              <div className="text-xs text-scurry-latte mt-0.5 truncate">{a.summary}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="px-5 pb-4">
                      {d.externalUrl && (
                        <Button size="sm" className="bg-scurry-orange hover:bg-scurry-orange-hover text-white" onClick={(e) => { e.stopPropagation(); window.open(d.externalUrl!, '_blank') }}>
                          <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                          View in Pipedrive
                        </Button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* THREADS */}
      {tab === 'threads' && (
        <div className="flex flex-col gap-3">
          {c.threads.length === 0 ? (
            <div className="bg-white rounded-xl border border-scurry-gray-border p-5">
              <p className="text-sm text-scurry-latte text-center py-5">No threads.</p>
            </div>
          ) : c.threads.map(t => (
            <div key={t.id} className="bg-white rounded-xl border border-scurry-gray-border overflow-hidden">
              <div className="p-5 cursor-pointer hover:bg-scurry-foam/40 transition-colors" onClick={() => setExpandedThread(expandedThread === t.id ? null : t.id)}>
                <div className="flex items-center gap-2 mb-2">
                  <StyledBadge className={SENTIMENT_STYLES[t.sentiment ?? ''] || ''}>{t.sentiment}</StyledBadge>
                  <StyledBadge className="bg-gray-100 text-scurry-gray-muted">{THREAD_STATUS_LABELS[t.status ?? '']}</StyledBadge>
                  <span className="text-[11px] text-scurry-gray-muted ml-auto">{t.msgs} msgs · {t.lastAt}</span>
                  <ChevronDown className={`h-4 w-4 text-scurry-latte transition-transform ${expandedThread === t.id ? 'rotate-180' : ''}`} />
                </div>
                <p className="text-sm text-scurry-espresso leading-relaxed">{t.summary}</p>
              </div>
              {expandedThread === t.id && (
                t.messages.length > 0 ? (
                  <div className="border-t border-scurry-gray-border bg-scurry-gray-light p-5">
                    <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-3">📧 Email Thread</div>
                    <div className="flex flex-col gap-3">{t.messages.map(m => <EmailMessage key={m.id} msg={m} />)}</div>
                  </div>
                ) : (
                  <div className="border-t border-scurry-gray-border bg-scurry-gray-light p-5 text-center text-sm text-scurry-gray-muted">Not yet synced.</div>
                )
              )}
            </div>
          ))}
        </div>
      )}

      {/* MEETINGS */}
      {tab === 'meetings' && (
        <div className="flex flex-col gap-4">
          {c.meetings.length === 0 ? (
            <div className="bg-white rounded-xl border border-scurry-gray-border p-5 text-center py-10">
              <p className="text-sm text-scurry-latte mb-3">No meetings synced yet.</p>
              <p className="text-xs text-scurry-gray-muted mb-4">Sync your Fireflies transcripts to see meeting intelligence here.</p>
            </div>
          ) : c.meetings.map(m => (
            <div key={m.id} className="bg-white rounded-xl border border-scurry-gray-border p-5">
              <div className="flex items-center gap-2 mb-3">
                <span className="font-semibold text-sm text-scurry-espresso">{m.date}</span>
                <StyledBadge className="bg-emerald-50 text-emerald-600">{m.source}</StyledBadge>
                <StyledBadge className="bg-purple-50 text-purple-700">Stage: {m.stage}</StyledBadge>
              </div>
              <p className="text-sm text-scurry-espresso leading-relaxed mb-4">{m.summary}</p>
              <div className="grid grid-cols-2 gap-5">
                <div>
                  <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-2">Key Points</div>
                  {m.keyPoints.map((k, i) => <div key={i} className="text-xs text-scurry-latte py-px">• {k}</div>)}
                </div>
                <div>
                  <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-2">Buying Signals</div>
                  {m.signals.map((s, i) => <div key={i} className="text-xs text-scurry-green py-px">✓ {s}</div>)}
                </div>
              </div>
              {m.objections.length > 0 && (
                <div className="mt-3">
                  <div className="text-[11px] text-scurry-latte font-bold uppercase tracking-wider mb-2">Objections</div>
                  <div className="flex gap-1.5">{m.objections.map(o => <StyledBadge key={o} className="bg-scurry-red-light text-scurry-red">{o}</StyledBadge>)}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── MAIN PAGE ──────────────────────────────────────────────────────────

type FilterType = string | null

const ContactPersonsPage: React.FC = () => {
  const [selectedContactId, setSelectedContactId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<FilterType>(null)

  const queryClient = useQueryClient()

  const { data: contactsResponse } = useQuery({
    queryKey: ['contacts-persons', search, statusFilter],
    queryFn: () => contactsApi.list({
      search: search || undefined,
      status: statusFilter || undefined,
    }).then(r => r.data),
  })
  const contacts = contactsResponse?.items ?? []
  const counts = contactsResponse?.counts ?? { active: 0, paused: 0, dnc: 0, bounced: 0 }

  const syncMeetings = useMutation({
    mutationFn: () => contactsApi.syncMeetings(50).then(r => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['contacts-persons'] })
      queryClient.invalidateQueries({ queryKey: ['contact-detail'] })
      alert(`Synced ${data.meetingsCreated} meetings from ${data.transcriptsSynced} transcripts`)
    },
    onError: () => alert('Meeting sync failed — check Fireflies API key in settings'),
  })

  const { data: selectedContact } = useQuery({
    queryKey: ['contact-detail', selectedContactId],
    queryFn: () => contactsApi.getById(selectedContactId!).then(r => r.data),
    enabled: !!selectedContactId,
  })

  const filtered = useMemo(() => contacts.filter(c => {
    const q = search.toLowerCase()
    return (!q || (c.name || '').toLowerCase().includes(q) || c.email.includes(q) || (c.orgName || '').toLowerCase().includes(q)) && (!statusFilter || c.status === statusFilter)
  }), [contacts, search, statusFilter])

  if (selectedContactId && selectedContact) {
    return <ContactDetail contact={selectedContact} onBack={() => setSelectedContactId(null)} />
  }

  const statCards = [
    { n: counts.active, title: 'Active', sub: 'Engaged contacts', color: 'bg-scurry-blue-text' },
    { n: counts.paused, title: 'Paused', sub: 'Sequences on hold', color: 'bg-scurry-green' },
    { n: counts.dnc, title: 'Do Not Contact', sub: 'Blocked', color: 'bg-scurry-red' },
    { n: counts.bounced, title: 'Bounced', sub: 'Requires attention', color: 'bg-scurry-energy-burst' },
  ]

  const filters: [string, string][] = [['', 'All'], ['active', 'Active'], ['paused', 'Paused'], ['do_not_contact', 'DNC'], ['bounced', 'Bounced']]

  return (
    <div>
      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h1 className="text-2xl font-bold text-scurry-espresso">Persons</h1>
          <p className="text-sm text-scurry-latte mt-1">Manage your contacts and track engagement</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="border-scurry-gray-border text-scurry-espresso hover:bg-scurry-foam"
            onClick={() => syncMeetings.mutate()}
            disabled={syncMeetings.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${syncMeetings.isPending ? 'animate-spin' : ''}`} />
            {syncMeetings.isPending ? 'Syncing...' : 'Sync Meetings'}
          </Button>
          <Button className="bg-scurry-orange hover:bg-scurry-orange-hover text-white shadow-lg shadow-scurry-orange/20">
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {statCards.map((s, i) => (
          <div key={i} className="bg-white rounded-xl border border-scurry-gray-border overflow-hidden">
            <div className={`h-1 ${s.color}`} />
            <div className="p-5">
              <span className="text-sm font-medium text-scurry-latte">{s.title}</span>
              <div className="text-[28px] font-bold text-scurry-espresso leading-none mt-1">{s.n}</div>
              <div className="text-xs text-scurry-gray-muted mt-1">{s.sub}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Search + filters */}
      <div className="flex gap-3 mb-5 flex-wrap items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-scurry-gray-muted" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, email, organization..."
            className="pl-9 border-scurry-gray-border focus:border-scurry-orange focus:ring-scurry-orange/10"
          />
        </div>
        <div className="flex gap-1.5">
          {filters.map(([k, l]) => (
            <button
              key={k}
              onClick={() => setStatusFilter(k || null)}
              className={`border-none px-4 py-1.5 rounded-full text-sm font-semibold cursor-pointer transition-all ${
                statusFilter === (k || null)
                  ? 'bg-scurry-orange text-white'
                  : 'bg-transparent text-scurry-latte hover:bg-scurry-foam'
              }`}
            >
              {l}
            </button>
          ))}
        </div>
      </div>

      {/* Contact list */}
      <div className="bg-white rounded-xl border border-scurry-gray-border overflow-hidden">
        {filtered.length === 0 ? (
          <div className="py-12 text-center text-sm text-scurry-latte">No contacts found</div>
        ) : filtered.map((c, i) => (
          <div
            key={c.id}
            onClick={() => setSelectedContactId(c.id)}
            className={`flex items-center gap-4 px-5 py-3.5 cursor-pointer transition-colors hover:bg-scurry-foam/50 ${
              i < filtered.length - 1 ? 'border-b border-scurry-gray-border' : ''
            }`}
          >
            <div className="w-10 h-10 rounded-full bg-scurry-orange flex items-center justify-center text-sm font-bold text-white shrink-0">
              {(c.name || c.email).split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-scurry-espresso">{c.name || c.email}</span>
                {c.pipedrive && <span className="text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-px rounded">PD</span>}
              </div>
              <div className="text-sm text-scurry-latte mt-0.5 truncate">{c.email} · {c.orgName}</div>
            </div>
            <div className="text-right shrink-0 flex items-center gap-4">
              <div>
                <div className="text-sm text-scurry-espresso font-medium">{c.stats.openDeals} deals · ${(c.stats.dealValue / 1000).toFixed(0)}K</div>
                <div className="text-[11px] text-scurry-gray-muted mt-0.5">{c.lastActivity}</div>
              </div>
              <StatusBadge status={c.status} />
              <ChevronRight className="h-4 w-4 text-scurry-gray-border" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ContactPersonsPage
