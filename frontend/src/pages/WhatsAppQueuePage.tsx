import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle,
  Clock,
  Edit3,
  Loader2,
  MessageCircle,
  Send,
  SkipForward,
  Trash2,
} from 'lucide-react'

import { whatsappQueueApi, WhatsAppQueueItem } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/use-toast'
import LoadingSpinner from '@/components/ui/loading-spinner'

type TabType = 'pending' | 'approved' | 'sent' | 'skipped' | 'failed'

const WhatsAppQueuePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('pending')
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editBody, setEditBody] = useState('')
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const getApprovalStatusFilter = (tab: TabType) => {
    switch (tab) {
      case 'pending': return 'pending'
      case 'approved': return 'approved'
      case 'skipped': return 'skipped'
      default: return undefined
    }
  }

  const getStatusFilter = (tab: TabType) => {
    switch (tab) {
      case 'pending': return 'pending'
      case 'approved': return 'pending'
      case 'skipped': return 'cancelled'
      case 'sent': return 'sent'
      case 'failed': return 'failed'
      default: return undefined
    }
  }

  const { data: messages, isLoading } = useQuery({
    queryKey: ['whatsappQueue', activeTab],
    queryFn: async () => {
      const response = await whatsappQueueApi.getAll(
        getStatusFilter(activeTab),
        getApprovalStatusFilter(activeTab)
      )
      return response.data
    },
    refetchInterval: 10000,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['whatsappQueue'] })
  }

  const approveMutation = useMutation({
    mutationFn: (id: number) => whatsappQueueApi.approve(id),
    onSuccess: () => {
      toast({ title: 'Success', description: 'WhatsApp message approved' })
      invalidate()
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to approve WhatsApp message',
        variant: 'destructive',
      })
    },
  })

  const skipMutation = useMutation({
    mutationFn: (id: number) => whatsappQueueApi.skip(id),
    onSuccess: () => {
      toast({ title: 'Success', description: 'WhatsApp message skipped' })
      invalidate()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => whatsappQueueApi.delete(id),
    onSuccess: () => {
      toast({ title: 'Success', description: 'WhatsApp message deleted' })
      invalidate()
    },
  })

  const editMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: string }) =>
      whatsappQueueApi.edit(id, body),
    onSuccess: () => {
      toast({ title: 'Success', description: 'WhatsApp message updated' })
      setEditingId(null)
      setEditBody('')
      invalidate()
    },
  })

  const processMutation = useMutation({
    mutationFn: () => whatsappQueueApi.processQueue(),
    onSuccess: (response) => {
      toast({
        title: 'Queue processed',
        description: `Sent ${response.data.sent}, failed ${response.data.failed}`,
      })
      invalidate()
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to process WhatsApp queue',
        variant: 'destructive',
      })
    },
  })

  const startEdit = (message: WhatsAppQueueItem) => {
    setEditingId(message.id)
    setEditBody(message.body || '')
  }

  const getStatusBadge = (message: WhatsAppQueueItem) => {
    if (message.status === 'sent') {
      return <Badge className="bg-blue-100 text-blue-700 border-blue-200">Sent</Badge>
    }
    if (message.status === 'failed') {
      return <Badge className="bg-red-100 text-red-700 border-red-200">Failed</Badge>
    }
    if (message.approval_status === 'approved') {
      return <Badge className="bg-green-100 text-green-700 border-green-200">Approved</Badge>
    }
    if (message.approval_status === 'skipped') {
      return <Badge className="bg-gray-100 text-gray-700 border-gray-200">Skipped</Badge>
    }
    return <Badge className="bg-orange-100 text-orange-700 border-orange-200">Pending</Badge>
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Not scheduled'
    return new Date(dateString).toLocaleString()
  }

  const counts = {
    pending: messages?.filter(m => m.approval_status === 'pending' && m.status === 'pending').length || 0,
    approved: messages?.filter(m => m.approval_status === 'approved' && m.status === 'pending').length || 0,
    sent: messages?.filter(m => m.status === 'sent').length || 0,
    skipped: messages?.filter(m => m.approval_status === 'skipped').length || 0,
    failed: messages?.filter(m => m.status === 'failed').length || 0,
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">
              WhatsApp Queue
            </h1>
            <p className="text-sm sm:text-base text-scurry-latte mt-2">
              Review, approve, and send WhatsApp follow-ups
            </p>
          </div>

          <Button
            onClick={() => processMutation.mutate()}
            disabled={processMutation.isPending}
            className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white gap-2"
          >
            {processMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Process Queue
          </Button>
        </div>
      </div>

      <div className="bg-white rounded-t-lg shadow-md border-0">
        <div className="flex px-2 border-b border-scurry-gray-border/50">
          {(['pending', 'approved', 'sent', 'skipped', 'failed'] as TabType[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 font-medium text-sm capitalize transition-colors border-b-2 ${
                activeTab === tab
                  ? 'border-scurry-orange text-scurry-orange'
                  : 'border-transparent text-scurry-latte hover:text-scurry-espresso'
              }`}
            >
              {tab} ({counts[tab] || 0})
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12 bg-white rounded-b-lg shadow-md">
          <LoadingSpinner />
        </div>
      ) : messages && messages.length > 0 ? (
        <div className="bg-white rounded-b-lg shadow-md overflow-hidden">
          <div className="divide-y divide-scurry-gray-border/50">
            {messages.map((message) => (
              <div key={message.id} className="p-5 hover:bg-scurry-orange-light/20">
                <div
                  className="flex items-center gap-4 cursor-pointer"
                  onClick={() => setExpandedId(expandedId === message.id ? null : message.id)}
                >
                  <div className="w-12 h-12 rounded-full bg-gradient-to-br from-scurry-orange to-orange-400 flex items-center justify-center text-white">
                    <MessageCircle className="h-5 w-5" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-scurry-espresso">
                      {message.recipient_name || message.recipient_phone || 'Unknown recipient'}
                    </div>
                    <div className="text-sm text-scurry-latte truncate">
                      {message.body || message.error_message || 'No message body'}
                    </div>
                    <div className="text-xs text-scurry-latte mt-1 flex gap-3">
                      <span>{message.recipient_phone}</span>
                      <span>{message.is_template_message ? 'Template' : 'Freeform'}</span>
                      {message.whatsapp_template_name && <span>{message.whatsapp_template_name}</span>}
                    </div>
                  </div>

                  <div className="flex flex-col items-end gap-2">
                    {getStatusBadge(message)}
                    <span className="text-xs text-scurry-latte flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDate(message.sent_at || message.scheduled_at)}
                    </span>
                  </div>
                </div>

                {expandedId === message.id && (
                  <div className="mt-5 border-t pt-4 space-y-4">
                    {editingId === message.id ? (
                      <div className="space-y-3">
                        <Textarea
                          value={editBody}
                          onChange={(e) => setEditBody(e.target.value)}
                          rows={6}
                        />
                        <div className="text-xs text-scurry-latte">
                          {editBody.length}/4096 characters
                        </div>
                        <div className="flex gap-2">
                          <Button
                            onClick={() => editMutation.mutate({ id: message.id, body: editBody })}
                            disabled={editMutation.isPending || !editBody.trim()}
                            className="bg-scurry-orange text-white"
                          >
                            Save
                          </Button>
                          <Button variant="outline" onClick={() => setEditingId(null)}>
                            Cancel
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap text-sm text-scurry-espresso bg-scurry-foam/40 p-4 rounded-lg">
                        {message.body || 'No message body'}
                      </div>
                    )}

                    {message.error_message && (
                      <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
                        {message.error_message}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-2">
                      {message.status === 'pending' && message.approval_status === 'pending' && (
                        <Button
                          size="sm"
                          onClick={() => approveMutation.mutate(message.id)}
                          disabled={approveMutation.isPending}
                          className="bg-scurry-green hover:bg-scurry-green/90 gap-1"
                        >
                          <CheckCircle className="h-4 w-4" />
                          Approve
                        </Button>
                      )}

                      {message.status !== 'sent' && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => startEdit(message)}
                            className="gap-1"
                          >
                            <Edit3 className="h-4 w-4" />
                            Edit
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => skipMutation.mutate(message.id)}
                            className="gap-1"
                          >
                            <SkipForward className="h-4 w-4" />
                            Skip
                          </Button>

                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => deleteMutation.mutate(message.id)}
                            className="gap-1 text-red-600 border-red-200 hover:bg-red-50"
                          >
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-b-lg shadow-md text-center py-12">
          <MessageCircle className="h-12 w-12 text-scurry-gray-muted mx-auto mb-4" />
          <h3 className="text-sm font-medium text-scurry-espresso mb-2">
            No WhatsApp messages
          </h3>
          <p className="text-sm text-scurry-gray-muted">
            WhatsApp queue items will appear here after workflow execution.
          </p>
        </div>
      )}
    </div>
  )
}

export default WhatsAppQueuePage