import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Mail,
  Clock,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Settings,
  Send,
  Edit3,
  SkipForward,
  Trash2,
  Loader2,
  Calendar,
  ExternalLink,
  AlertTriangle,
  RotateCcw,
  ShieldCheck,
  ShieldAlert
} from 'lucide-react'
import { emailQueueApi, contactsApi, EmailQueueItem, EmailQueueStats, ContactActivity } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import LoadingSpinner from '@/components/ui/loading-spinner'

type TabType = 'pending' | 'approved' | 'sent' | 'skipped' | 'failed'

const EmailQueuePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('pending')
  const [reviewFilter, setReviewFilter] = useState<'all' | 'requires' | 'no-review'>('all')
  const [expandedEmailId, setExpandedEmailId] = useState<number | null>(null)
  const [aiEditPrompt, setAiEditPrompt] = useState('')
  const [editingEmailId, setEditingEmailId] = useState<number | null>(null)
  const [editSubject, setEditSubject] = useState('')
  const [editBody, setEditBody] = useState('')
  const [modifiedPreview, setModifiedPreview] = useState<{ subject: string; body: string; summary: string } | null>(null)
  const [showApproveAllModal, setShowApproveAllModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [emailToDelete, setEmailToDelete] = useState<number | null>(null)

  const { toast } = useToast()
  const queryClient = useQueryClient()

  // Fetch stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['emailQueueStats'],
    queryFn: async () => {
      const response = await emailQueueApi.getStats()
      return response.data
    },
    refetchInterval: 10000,
  })

  // Get approval status based on active tab
  const getApprovalStatusFilter = (tab: TabType) => {
    switch (tab) {
      case 'pending': return 'pending'
      case 'approved': return 'approved'
      case 'skipped': return 'skipped'
      default: return undefined
    }
  }

  // Get status filter based on active tab
  const getStatusFilter = (tab: TabType) => {
    switch (tab) {
      case 'pending': return 'pending'   // Filter out cancelled emails
      case 'approved': return 'pending'  // Approved emails still have status=pending until sent
      case 'skipped': return 'cancelled'  // Skipped emails have status=cancelled
      case 'sent': return 'sent'
      case 'failed': return 'failed'
      default: return undefined
    }
  }

  // Fetch emails based on active tab
  const { data: emails, isLoading: emailsLoading } = useQuery({
    queryKey: ['emailQueue', activeTab, reviewFilter],
    queryFn: async () => {
      const response = await emailQueueApi.getAll(
        getStatusFilter(activeTab),
        getApprovalStatusFilter(activeTab)
      )
      let data = response.data

      if (reviewFilter === 'requires') {
        data = data.filter((e: EmailQueueItem) => e.approval_status === 'pending')
      }

      if (reviewFilter === 'no-review') {
        data = data.filter((e: EmailQueueItem) => e.approval_status !== 'pending')
      }

      return data
    },
    refetchInterval: 10000,
  })

  // Mutations
  const approveMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.approve(emailId),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email approved successfully' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to approve email', variant: 'destructive' })
    },
  })

  const skipMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.skip(emailId),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email skipped' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to skip email', variant: 'destructive' })
    },
  })

  const unapproveMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.unapprove(emailId),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email moved back to pending' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to unapprove email', variant: 'destructive' })
    },
  })

  const unskipMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.unskip(emailId),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email moved back to pending' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to unskip email', variant: 'destructive' })
    },
  })

  // Fresh Check override — clears the audit fields and requeues for
  // immediate send. Backend refuses on DNC stops.
  const overrideFreshCheckMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.overrideFreshCheck(emailId),
    onSuccess: (res) => {
      toast({
        title: 'Fresh Check overridden',
        description: res.data?.message || 'Email requeued for immediate send',
      })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
    },
    onError: (error: any) => {
      toast({
        title: 'Override rejected',
        description:
          error.response?.data?.detail ||
          'Could not override the Fresh Check decision',
        variant: 'destructive',
      })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.cancel(emailId),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email deleted' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
      setShowDeleteModal(false)
      setEmailToDelete(null)
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to delete email', variant: 'destructive' })
    },
  })

  const approveAllMutation = useMutation({
    mutationFn: () => emailQueueApi.approveAll(),
    onSuccess: (response) => {
      toast({ title: 'Success', description: `Approved ${response.data.approved_count} emails` })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      queryClient.invalidateQueries({ queryKey: ['emailQueueStats'] })
      setShowApproveAllModal(false)
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to approve all', variant: 'destructive' })
    },
  })

  const aiEditMutation = useMutation({
    mutationFn: ({ emailId, prompt }: { emailId: number; prompt: string }) =>
      emailQueueApi.aiEdit(emailId, prompt),
    onSuccess: (response) => {
      setModifiedPreview({
        subject: response.data.modified_subject,
        body: response.data.modified_body,
        summary: response.data.changes_summary
      })
      toast({ title: 'AI Edit Applied', description: response.data.changes_summary })
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'AI edit failed', variant: 'destructive' })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ emailId, subject, body, editSource }: { emailId: number; subject: string; body: string; editSource?: string }) =>
      emailQueueApi.update(emailId, { subject, body, edit_source: editSource }),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email updated' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      setEditingEmailId(null)
      setModifiedPreview(null)
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to update email', variant: 'destructive' })
    },
  })

  const revertMutation = useMutation({
    mutationFn: (emailId: number) => emailQueueApi.revert(emailId),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Email reverted to original' })
      queryClient.invalidateQueries({ queryKey: ['emailQueue'] })
      setModifiedPreview(null)
    },
    onError: (error: any) => {
      toast({ title: 'Error', description: error.response?.data?.detail || 'Failed to revert email', variant: 'destructive' })
    },
  })

  // Helper functions
  const getInitials = (name?: string, email?: string) => {
    if (name) {
      const parts = name.split(' ')
      if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      return name.slice(0, 2).toUpperCase()
    }
    return email?.slice(0, 2).toUpperCase() || '??'
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)

    if (date.toDateString() === now.toDateString()) {
      return `Today, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    } else if (date.toDateString() === tomorrow.toDateString()) {
      return `Tomorrow, ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ', ' +
      date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  }

  const formatActivityDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)

    if (date.toDateString() === now.toDateString()) {
      return `Today at ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    } else if (date.toDateString() === yesterday.toDateString()) {
      return `Yesterday at ${date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' at ' +
      date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  }

  const getApprovalBadge = (email: EmailQueueItem) => {
    if (email.status === 'sent') {
      return <Badge className="bg-blue-100 text-blue-700 border-blue-200">Sent</Badge>
    }
    if (email.status === 'failed') {
      return <Badge className="bg-red-100 text-red-700 border-red-200">Failed</Badge>
    }
    switch (email.approval_status) {
      case 'pending':
        return <Badge className="bg-orange-100 text-orange-700 border-orange-200">Pending</Badge>
      case 'approved':
        return <Badge className="bg-green-100 text-green-700 border-green-200">Approved</Badge>
      case 'skipped':
        return <Badge className="bg-gray-100 text-gray-700 border-gray-200">Skipped</Badge>
      default:
        return null
    }
  }

  const getRequiresReviewBadge = (email: EmailQueueItem) => {
    if (!email.requires_review) return null

    return (
      <Badge className="bg-yellow-100 text-yellow-800 border-yellow-300 gap-1">
        <ShieldAlert className="h-3 w-3" />
        Needs Approval
      </Badge>
    )
  }

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'email_sent': return <Send className="h-4 w-4" />
      case 'email_opened': return <ExternalLink className="h-4 w-4" />
      case 'reply_received': return <Mail className="h-4 w-4" />
      case 'meeting': return <Calendar className="h-4 w-4" />
      case 'bounced': return <XCircle className="h-4 w-4" />
      default: return <Mail className="h-4 w-4" />
    }
  }

  // Fresh Check badge — rendered on queue rows that went through the
  // pre-send gate. `continue` is rendered as a quiet "passed" badge so
  // admins can see the gate ran; terminal actions are loud.
  const getFreshCheckBadge = (email: EmailQueueItem) => {
    const action = email.fresh_check_action
    if (!action) return null

    const rule = email.fresh_check_rule_triggered
    const isDnc = rule === 'dnc'

    if (action === 'continue') {
      return (
        <Badge
          title={email.fresh_check_reason || 'Fresh Check: no rule triggered'}
          className="bg-scurry-foam text-scurry-latte border-scurry-gray-border gap-1"
        >
          <ShieldCheck className="h-3 w-3" />
          Fresh Check: passed
        </Badge>
      )
    }

    const actionLabel: Record<string, string> = {
      cancel_sequence: 'Cancelled sequence',
      cancel_email: 'Cancelled email',
      skip_email: 'Skipped',
      reschedule: 'Rescheduled',
    }
    const label = actionLabel[action] || action

    return (
      <Badge
        title={email.fresh_check_reason || ''}
        className={
          'gap-1 ' +
          (isDnc
            ? 'bg-red-50 text-red-700 border-red-200'
            : 'bg-amber-50 text-amber-700 border-amber-200')
        }
      >
        {isDnc ? (
          <ShieldAlert className="h-3 w-3" />
        ) : (
          <ShieldCheck className="h-3 w-3" />
        )}
        {label}
        {rule && !isDnc && (
          <span className="opacity-70">· {rule.replace(/_/g, ' ')}</span>
        )}
        {isDnc && <span className="opacity-80 font-semibold">· DNC</span>}
      </Badge>
    )
  }

  const getThreadingBadge = (email: EmailQueueItem) => {
    if (!email.thread_parent_component_id) return null

    const fallbackReasonLabels: Record<string, string> = {
      parent_not_sent: "parent did not send",
      parent_bounced: "parent bounced",
      different_account: "different account",
      parent_missing_message_id: "missing message ID",
    }
    const parentName = email.thread_parent_component_name || "Unknown"
    const replyLabel = parentName.toLowerCase().startsWith("email ")
      ? `🔗 Replying to ${parentName}`
      : `🔗 Replying to Email ${parentName}`
    const fallbackLabel = email.thread_fallback_reason
      ? `⚠️ Fallback: ${fallbackReasonLabels[email.thread_fallback_reason] || email.thread_fallback_reason}`
      : "⚠️ Fallback"

    return (
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="bg-violet-50 text-violet-700 border-violet-200 gap-1">
          {replyLabel}
        </Badge>
        {email.thread_fallback_reason && (
          <Badge className="bg-amber-50 text-amber-700 border-amber-200 gap-1">
            {fallbackLabel}
          </Badge>
        )}
      </div>
    )
  }

  const handleAiEdit = (emailId: number) => {
    if (!aiEditPrompt.trim()) return
    aiEditMutation.mutate({ emailId, prompt: aiEditPrompt })
  }

  const handleAcceptAiEdit = (emailId: number) => {
    if (!modifiedPreview) return
    updateMutation.mutate({
      emailId,
      subject: modifiedPreview.subject,
      body: modifiedPreview.body,
      editSource: 'ai'
    })
  }

  const handleStartManualEdit = (email: EmailQueueItem) => {
    setEditingEmailId(email.id)
    setEditSubject(email.subject)
    setEditBody(email.body)
  }

  const handleSaveManualEdit = (emailId: number) => {
    updateMutation.mutate({
      emailId,
      subject: editSubject,
      body: editBody
    })
  }

  const handleDeleteClick = (emailId: number) => {
    setEmailToDelete(emailId)
    setShowDeleteModal(true)
  }

  const getTabCount = (tab: TabType) => {
    if (!stats) return 0
    switch (tab) {
      case 'pending': return stats.pending
      case 'approved': return stats.approved
      case 'sent': return stats.sent
      case 'skipped': return stats.skipped
      case 'failed': return stats.failed
      default: return 0
    }
  }

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <LoadingSpinner />
      </div>
    )
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header with Light Gradient */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />

        <div className="flex justify-between items-start relative z-10">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">Email Queue</h1>
            <p className="text-sm sm:text-base text-scurry-latte mt-2">Review and approve your scheduled emails</p>
          </div>
          <div className="flex gap-3">
            <Button variant="outline" className="gap-2">
              <Settings className="h-4 w-4" />
              Settings
            </Button>
            
            <div className="flex items-center gap-2">
              <span className="text-sm text-scurry-latte">Review Requirement:</span>
              <select
                value={reviewFilter}
                onChange={(e) => setReviewFilter(e.target.value as any)}
                className="border px-3 py-2 rounded-md text-sm"
              >
                <option value="all">All Emails</option>
                <option value="requires">Requires Review</option>
                <option value="no-review">No Review Required</option>
              </select>
            </div>
            <Button
              className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange shadow-md hover:shadow-lg hover:scale-105 transition-all duration-200 gap-2"
              onClick={() => setShowApproveAllModal(true)}
              disabled={!stats?.pending}
            >
              <CheckCircle className="h-4 w-4" />
              Approve All ({stats?.pending || 0})
            </Button>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
        <div className="bg-white overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow rounded-lg">
          <div className="h-1.5 bg-gradient-to-r from-scurry-orange to-scurry-energy-burst" />
          <div className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-4">
            <div className="text-sm font-medium text-scurry-latte">Pending Approval</div>
            <div className="p-2 rounded-full bg-scurry-orange-light">
              <Clock className="h-4 w-4 text-scurry-orange" />
            </div>
          </div>
          <div className="px-4 pb-4">
            <div className="text-3xl font-bold text-scurry-espresso">{stats?.pending || 0}</div>
            <p className="text-xs text-scurry-latte mt-1">Awaiting review</p>
          </div>
        </div>

        <div className="bg-white overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow rounded-lg">
          <div className="h-1.5 bg-gradient-to-r from-scurry-green to-scurry-energy-burst" />
          <div className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-4">
            <div className="text-sm font-medium text-scurry-latte">Approved</div>
            <div className="p-2 rounded-full bg-scurry-green-light">
              <CheckCircle className="h-4 w-4 text-scurry-green" />
            </div>
          </div>
          <div className="px-4 pb-4">
            <div className="text-3xl font-bold text-scurry-espresso">{stats?.approved || 0}</div>
            <p className="text-xs text-scurry-latte mt-1">Ready to send</p>
          </div>
        </div>

        <div className="bg-white overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow rounded-lg">
          <div className="h-1.5 bg-gradient-to-r from-scurry-blue-text to-scurry-latte" />
          <div className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-4">
            <div className="text-sm font-medium text-scurry-latte">Sent Today</div>
            <div className="p-2 rounded-full bg-scurry-blue-bg">
              <Send className="h-4 w-4 text-scurry-blue-text" />
            </div>
          </div>
          <div className="px-4 pb-4">
            <div className="text-3xl font-bold text-scurry-espresso">{stats?.sent_today || 0}</div>
            <p className="text-xs text-scurry-latte mt-1">Delivered today</p>
          </div>
        </div>

        <div className="bg-white overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow rounded-lg">
          <div className="h-1.5 bg-gradient-to-r from-scurry-red to-scurry-orange" />
          <div className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-4">
            <div className="text-sm font-medium text-scurry-latte">Failed</div>
            <div className="p-2 rounded-full bg-scurry-red-light">
              <AlertTriangle className="h-4 w-4 text-scurry-red" />
            </div>
          </div>
          <div className="px-4 pb-4">
            <div className="text-3xl font-bold text-scurry-espresso">{stats?.failed || 0}</div>
            <p className="text-xs text-scurry-latte mt-1">Requires attention</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-t-lg shadow-md border-0">
        <div className="flex px-2 border-b border-scurry-gray-border/50">
          {(['pending', 'approved', 'sent', 'skipped', 'failed'] as TabType[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 font-medium text-sm capitalize transition-colors border-b-2 ${activeTab === tab
                ? 'border-scurry-orange text-scurry-orange'
                : 'border-transparent text-scurry-latte hover:text-scurry-espresso'
                }`}
            >
              {tab} ({getTabCount(tab)})
            </button>
          ))}
        </div>
      </div>

      {/* Content Area */}
      <div>
        {emailsLoading ? (
          <div className="flex justify-center py-12 bg-white rounded-b-lg shadow-md">
            <LoadingSpinner />
          </div>
        ) : emails && emails.length > 0 ? (
          <div className="bg-white rounded-b-lg shadow-md overflow-hidden">
            <div className="divide-y divide-scurry-gray-border/50">
              {emails.map((email) => {
                const threadingBadge = getThreadingBadge(email)
                return (
                <div
                  key={email.id}
                  className={`overflow-hidden transition-all ${email.requires_review ? 'border-l-4 border-yellow-400' : ''
                    } ${expandedEmailId === email.id
                      ? 'bg-scurry-foam/30'
                      : 'hover:bg-scurry-orange-light/20'
                    }`}
                >
                  {/* Card Header */}
                  <div
                    className="px-6 py-4 flex items-center gap-4 cursor-pointer border-b border-transparent hover:bg-scurry-orange-light/20"
                    onClick={() => setExpandedEmailId(expandedEmailId === email.id ? null : email.id)}
                    style={{ borderBottomColor: expandedEmailId === email.id ? 'rgb(var(--scurry-gray-border) / 0.5)' : 'transparent' }}
                  >
                    {/* Avatar */}
                    <div className="w-12 h-12 rounded-full bg-gradient-to-br from-scurry-orange to-orange-400 flex items-center justify-center text-white font-semibold flex-shrink-0">
                      {getInitials(email.recipient_name || email.contact?.name, email.recipient_email)}
                    </div>

                    {/* Email Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-scurry-espresso">
                          {email.recipient_name || email.contact?.name || email.recipient_email.split('@')[0]}
                        </span>
                        {email.contact?.company && (
                          <span className="text-xs text-scurry-latte bg-scurry-foam px-2 py-0.5 rounded">
                            {email.contact.company}
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-scurry-latte mt-0.5 truncate">{email.subject}</div>
                      <div className="flex items-center gap-4 mt-1 text-xs text-scurry-latte">
                        <span className="flex items-center gap-1">
                          <Mail className="h-3 w-3" /> {email.recipient_email}
                        </span>
                        {email.sequence_name && (
                          <span className="flex items-center gap-1">
                            <span aria-hidden="true">📋</span> {email.sequence_name}
                          </span>
                        )}
                        {email.sequence_position && email.sequence_total && (
                          <span className="flex items-center gap-1">
                            <span aria-hidden="true">✉️</span> Email {email.sequence_position} of {email.sequence_total}
                          </span>
                        )}
                      </div>
                      {threadingBadge && (
                        <div className="mt-2">
                          {threadingBadge}
                        </div>
                      )}
                    </div>

                    {/* Status & Time */}
                    <div className="flex flex-col items-end gap-2 flex-shrink-0">
                      {getApprovalBadge(email)}
                      {getRequiresReviewBadge(email)}
                      {getFreshCheckBadge(email)}
                      <span className="text-xs text-scurry-latte flex items-center gap-1">
                        {email.status === 'sent' ? 'Sent:' : 'Scheduled:'} {formatDate(email.sent_at || email.scheduled_at)}
                        {email.timing_reason && (
                          <span title={email.timing_reason} className="cursor-help">
                            <Clock className="h-3 w-3 text-scurry-orange" />
                          </span>
                        )}
                      </span>
                      {email.fresh_check_action === 'reschedule' && email.fresh_check_resume_date && (
                        <span className="text-[11px] text-amber-700">
                          Resumes {email.fresh_check_resume_date}
                        </span>
                      )}
                    </div>

                    {/* Inline Action Buttons (collapsed view) */}
                    {email.requires_review && email.approval_status === 'pending' && email.status === 'pending' && (
                      <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="sm"
                          onClick={() => approveMutation.mutate(email.id)}
                          disabled={approveMutation.isPending}
                          className="bg-scurry-green hover:bg-scurry-green/90 gap-1 text-xs h-8 px-2"
                          title="Approve & Send"
                        >
                          <CheckCircle className="h-3.5 w-3.5" />
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => skipMutation.mutate(email.id)}
                          disabled={skipMutation.isPending}
                          className="gap-1 text-xs h-8 px-2 bg-scurry-gray-light text-scurry-latte hover:bg-scurry-gray-border hover:text-scurry-espresso"
                          title="Skip This Email"
                        >
                          <SkipForward className="h-3.5 w-3.5" />
                          Skip
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDeleteClick(email.id)}
                          className="gap-1 text-xs h-8 px-2 text-scurry-red border-scurry-red-light hover:bg-scurry-red-light"
                          title="Delete Email"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
                    )}

                    {/* Fresh Check override — only offered on non-DNC
                      terminal actions. DNC is locked-on and must be
                      cleared via the contact/org DNC flag instead. */}
                    {email.fresh_check_action &&
                      email.fresh_check_action !== 'continue' &&
                      email.fresh_check_rule_triggered !== 'dnc' &&
                      email.status !== 'sent' && (
                        <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => overrideFreshCheckMutation.mutate(email.id)}
                            disabled={overrideFreshCheckMutation.isPending}
                            className="gap-1 text-xs h-8 px-2 border-amber-300 text-amber-700 hover:bg-amber-50"
                            title="Clear the Fresh Check decision and send this email now"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            Override
                          </Button>
                        </div>
                      )}

                    {email.approval_status === 'approved' && email.status === 'pending' && (
                      <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => unapproveMutation.mutate(email.id)}
                          disabled={unapproveMutation.isPending}
                          className="gap-1 text-xs h-8 px-2"
                          title="Unapprove"
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Unapprove
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDeleteClick(email.id)}
                          className="gap-1 text-xs h-8 px-2 text-scurry-red border-scurry-red-light hover:bg-scurry-red-light"
                          title="Cancel Email"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Cancel
                        </Button>
                      </div>
                    )}

                    {email.approval_status === 'skipped' && (
                      <div className="flex items-center gap-1 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => unskipMutation.mutate(email.id)}
                          disabled={unskipMutation.isPending}
                          className="gap-1 text-xs h-8 px-2"
                          title="Move to Pending"
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Restore
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDeleteClick(email.id)}
                          className="gap-1 text-xs h-8 px-2 text-scurry-red border-scurry-red-light hover:bg-scurry-red-light"
                          title="Delete Email"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
                    )}

                    {/* Expand Icon */}
                    <div className="text-scurry-latte">
                      {expandedEmailId === email.id ? (
                        <ChevronUp className="h-5 w-5" />
                      ) : (
                        <ChevronDown className="h-5 w-5" />
                      )}
                    </div>
                  </div>

                  {/* Expanded Content */}
                  {expandedEmailId === email.id && (
                    <div>
                      <div className="grid grid-cols-[1fr_320px] min-h-[400px]">
                        {/* Left Column - Email Content */}
                        <div className="p-6 border-r border-scurry-gray-border/50">
                          <div className="flex justify-between items-center mb-4">
                            <span className="font-semibold text-sm text-scurry-espresso">Email Preview</span>
                            {email.sequence_name && email.sequence_position && email.sequence_total && (
                              <span className="text-xs text-scurry-latte bg-scurry-gray-light px-2 py-1 rounded">
                                {email.sequence_name} • Email {email.sequence_position} of {email.sequence_total}
                              </span>
                            )}
                          </div>

                          {/* Email Preview Box */}
                          {editingEmailId === email.id ? (
                            <div className="space-y-4">
                              <div>
                                <label className="text-xs font-medium text-scurry-latte mb-1 block">Subject</label>
                                <Input
                                  value={editSubject}
                                  onChange={(e) => setEditSubject(e.target.value)}
                                  className="w-full"
                                />
                              </div>
                              <div>
                                <label className="text-xs font-medium text-scurry-latte mb-1 block">Body</label>
                                <Textarea
                                  value={editBody}
                                  onChange={(e) => setEditBody(e.target.value)}
                                  className="w-full min-h-[200px]"
                                />
                              </div>
                              <div className="flex gap-2">
                                <Button
                                  size="sm"
                                  onClick={() => handleSaveManualEdit(email.id)}
                                  disabled={updateMutation.isPending}
                                >
                                  {updateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Save'}
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setEditingEmailId(null)}
                                >
                                  Cancel
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div className="bg-scurry-foam/50 border border-scurry-gray-border/50 rounded-lg p-5 text-sm leading-relaxed max-h-[200px] overflow-y-auto">
                              <div className="font-semibold mb-4 pb-3 border-b border-scurry-gray-border/50">
                                Subject: {email.subject}
                              </div>
                              {email.org_warning && (
                                <Alert className="mb-4 bg-amber-50 border-amber-300 text-amber-900">
                                  <AlertTriangle className="h-4 w-4" />
                                  <AlertDescription>{email.org_warning}</AlertDescription>
                                </Alert>
                              )}
                              <div className="whitespace-pre-wrap">{email.body}</div>
                            </div>
                          )}

                          {/* AI Edit Section - only show for pending emails */}
                          {email.approval_status === 'pending' && email.status === 'pending' && editingEmailId !== email.id && (
                            <div className="mt-6 p-5 bg-gradient-to-br from-scurry-foam to-amber-50 rounded-lg border border-amber-200">
                              <div className="flex items-center gap-2 font-semibold text-sm mb-3">
                                <Sparkles className="h-4 w-4 text-scurry-orange" />
                                Quick AI Edit
                              </div>
                              <div className="flex gap-2">
                                <Input
                                  placeholder="e.g., mention she replied yesterday and liked the pricing"
                                  value={aiEditPrompt}
                                  onChange={(e) => setAiEditPrompt(e.target.value)}
                                  className="flex-1 bg-white"
                                />
                                <Button
                                  onClick={() => handleAiEdit(email.id)}
                                  disabled={aiEditMutation.isPending || !aiEditPrompt.trim()}
                                  className="bg-gradient-to-r from-scurry-orange to-orange-600 hover:from-orange-600 hover:to-orange-700 gap-2"
                                >
                                  {aiEditMutation.isPending ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Sparkles className="h-4 w-4" />
                                  )}
                                  Apply
                                </Button>
                              </div>
                              <p className="text-xs text-scurry-latte mt-3">
                                <span aria-hidden="true">💡</span> AI will make a small tweak based on your instruction (max ~30 words added)
                              </p>

                              {/* Modified Preview */}
                              {modifiedPreview && (
                                <div className="mt-4 p-4 bg-white border-2 border-green-500 rounded-lg relative">
                                  <div className="absolute -top-2.5 left-3 px-2 py-0.5 bg-green-500 text-white text-xs font-semibold rounded flex items-center gap-1">
                                    <CheckCircle className="h-3 w-3" /> AI Modified
                                  </div>
                                  <div className="text-sm leading-relaxed mt-2">
                                    <strong>Subject:</strong> {modifiedPreview.subject}
                                    <div className="mt-2 whitespace-pre-wrap">{modifiedPreview.body}</div>
                                  </div>
                                  <div className="flex gap-2 mt-4">
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      onClick={() => handleAcceptAiEdit(email.id)}
                                      disabled={updateMutation.isPending}
                                    >
                                      Accept
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => {
                                        setModifiedPreview(null)
                                        setAiEditPrompt('')
                                      }}
                                    >
                                      Undo
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      onClick={() => handleStartManualEdit(email)}
                                    >
                                      Edit Manually
                                    </Button>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Original indicator */}
                          {email.edit_source && email.original_subject && (
                            <div className="mt-4 flex items-center gap-2 text-xs text-scurry-latte">
                              <span className="font-medium">Edited ({email.edit_source})</span>
                              <Button
                                variant="link"
                                size="sm"
                                className="h-auto p-0 text-xs"
                                onClick={() => revertMutation.mutate(email.id)}
                                disabled={revertMutation.isPending}
                              >
                                Revert to original
                              </Button>
                            </div>
                          )}

                          {/* AI Reasoning Section */}
                          {(email.timing_reason || email.generation_reason) && (
                            <details className="mt-4 group">
                              <summary className="text-xs font-semibold text-scurry-latte uppercase tracking-wide cursor-pointer flex items-center gap-1 hover:text-scurry-espresso select-none">
                                <Sparkles className="h-3 w-3" />
                                AI Reasoning
                                <ChevronDown className="h-3 w-3 group-open:rotate-180 transition-transform" />
                              </summary>
                              <div className="mt-2 space-y-2 text-sm text-scurry-espresso bg-scurry-foam/50 rounded-lg p-3 border border-scurry-foam">
                                {email.timing_reason && (
                                  <div>
                                    <span className="text-xs font-medium text-scurry-latte">Timing:</span>
                                    <p className="mt-0.5">{email.timing_reason}</p>
                                  </div>
                                )}
                                {email.generation_reason && (
                                  <div>
                                    <span className="text-xs font-medium text-scurry-latte">Content decisions:</span>
                                    <p className="mt-0.5">{email.generation_reason}</p>
                                  </div>
                                )}
                              </div>
                            </details>
                          )}
                        </div>

                        {/* Right Column - Contact Panel */}
                        <div className="p-6 bg-scurry-foam/30">
                          <div className="flex items-center gap-4 mb-6">
                            <div className="w-14 h-14 rounded-full bg-gradient-to-br from-scurry-orange to-orange-400 flex items-center justify-center text-white font-semibold text-lg">
                              {getInitials(email.recipient_name || email.contact?.name, email.recipient_email)}
                            </div>
                            <div>
                              <h3 className="font-semibold text-scurry-espresso">
                                {email.recipient_name || email.contact?.name || 'Unknown'}
                              </h3>
                              {email.contact?.title && (
                                <div className="text-sm text-scurry-latte">{email.contact.title}</div>
                              )}
                              {email.contact?.company && (
                                <div className="text-sm text-scurry-orange font-medium">{email.contact.company}</div>
                              )}
                            </div>
                          </div>

                          {/* Activity Timeline */}
                          {email.activities && email.activities.length > 0 && (
                            <div className="mt-4">
                              <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-4">
                                Recent Activity
                              </div>
                              <div className="space-y-3">
                                {email.activities.map((activity) => (
                                  <div
                                    key={activity.id}
                                    className={`flex gap-3 p-3 bg-white rounded-lg border ${activity.is_new ? 'border-scurry-orange/50 bg-scurry-orange-light/30' : 'border-scurry-gray-border/50'
                                      }`}
                                  >
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${activity.activity_type === 'email_sent' ? 'bg-scurry-blue-bg' :
                                      activity.activity_type === 'reply_received' ? 'bg-scurry-green-light' :
                                        activity.activity_type === 'meeting' ? 'bg-scurry-orange-light' :
                                          'bg-scurry-gray-light'
                                      }`}>
                                      {getActivityIcon(activity.activity_type)}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                      <div className="text-sm font-medium text-scurry-espresso flex items-center gap-2">
                                        {activity.title || activity.activity_type.replace('_', ' ')}
                                        {activity.is_new && (
                                          <span className="text-[10px] bg-amber-400 text-scurry-espresso px-1.5 py-0.5 rounded font-bold">
                                            NEW
                                          </span>
                                        )}
                                      </div>
                                      <div className="text-xs text-scurry-latte mt-0.5">
                                        {formatActivityDate(activity.occurred_at)}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {(!email.activities || email.activities.length === 0) && (
                            <div className="text-center py-8 text-scurry-latte text-sm">
                              No recent activity
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Action Buttons */}
                      {email.approval_status === 'pending' && email.status === 'pending' && (
                        <div className="flex gap-3 p-4 bg-scurry-foam/50 border-t border-scurry-gray-border/50">
                          {email.requires_review && (
                            <Button
                              onClick={() => approveMutation.mutate(email.id)}
                              disabled={approveMutation.isPending}
                              className="bg-scurry-green hover:bg-scurry-green/90 gap-2"
                            >
                              <CheckCircle className="h-4 w-4" />
                              Approve & Send
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            onClick={() => handleStartManualEdit(email)}
                            className="gap-2"
                          >
                            <Edit3 className="h-4 w-4" />
                            Edit Manually
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => skipMutation.mutate(email.id)}
                            disabled={skipMutation.isPending}
                            className="gap-2 bg-scurry-gray-light text-scurry-latte hover:bg-scurry-gray-border hover:text-scurry-espresso"
                          >
                            <SkipForward className="h-4 w-4" />
                            Skip This Email
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => handleDeleteClick(email.id)}
                            className="ml-auto gap-2 text-scurry-red border-scurry-red-light hover:bg-scurry-red-light"
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </Button>
                        </div>
                      )}

                      {email.approval_status === 'skipped' && (
                        <div className="flex gap-3 p-4 bg-scurry-foam/50 border-t border-scurry-gray-border/50">
                          <Button
                            onClick={() => unskipMutation.mutate(email.id)}
                            disabled={unskipMutation.isPending}
                            className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange gap-2"
                          >
                            {unskipMutation.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <RotateCcw className="h-4 w-4" />
                            )}
                            Move to Pending
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => handleDeleteClick(email.id)}
                            className="ml-auto gap-2 text-scurry-red border-scurry-red-light hover:bg-scurry-red-light"
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </Button>
                        </div>
                      )}
                      {email.approval_status === 'approved' && email.status === 'pending' && (
                        <div className="flex gap-3 p-4 bg-scurry-foam/50 border-t border-scurry-gray-border/50">
                          <Button
                            onClick={() => unapproveMutation.mutate(email.id)}
                            disabled={unapproveMutation.isPending}
                            className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange gap-2"
                          >
                            {unapproveMutation.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <RotateCcw className="h-4 w-4" />
                            )}
                            Unapprove
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => handleDeleteClick(email.id)}
                            className="ml-auto gap-2 text-scurry-red border-scurry-red-light hover:bg-scurry-red-light"
                          >
                            <Trash2 className="h-4 w-4" />
                            Cancel Email
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )})}
            </div>
          </div>
        ) : (
          <div className="text-center py-16 bg-white rounded-b-lg shadow-md">
            <div className="p-4 rounded-full bg-scurry-orange-light inline-block mb-4">
              <Mail className="h-10 w-10 text-scurry-orange" />
            </div>
            <p className="text-scurry-espresso font-medium text-lg">No emails found</p>
            <p className="text-scurry-latte text-sm mt-1">
              {activeTab === 'pending' ? 'No emails waiting for approval' : `No ${activeTab} emails`}
            </p>
          </div>
        )}
      </div>

      {/* Approve All Modal */}
      <Dialog open={showApproveAllModal} onOpenChange={setShowApproveAllModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve All Pending Emails?</DialogTitle>
            <DialogDescription>
              This will approve <strong>{stats?.pending || 0} emails</strong> and schedule them for sending.
              You can still edit or cancel individual emails after approval.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowApproveAllModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => approveAllMutation.mutate()}
              disabled={approveAllMutation.isPending}
              className="bg-scurry-orange hover:bg-scurry-orange/90 gap-2"
            >
              {approveAllMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle className="h-4 w-4" />
              )}
              Approve All ({stats?.pending || 0})
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Modal */}
      <Dialog open={showDeleteModal} onOpenChange={setShowDeleteModal}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Email?</DialogTitle>
            <DialogDescription>
              This action cannot be undone. The email will be permanently removed from the queue.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteModal(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => emailToDelete && cancelMutation.mutate(emailToDelete)}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Delete Email'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default EmailQueuePage
