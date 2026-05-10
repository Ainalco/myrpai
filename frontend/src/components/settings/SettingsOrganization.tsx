import React, { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/components/ui/use-toast'
import { authApi, teamApi } from '@/lib/api'
import api from '@/lib/api'
import { Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const SettingsOrganization: React.FC = () => {
  const { user } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const role = user?.role || 'member'

  const [orgName, setOrgName] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
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

  if (role === 'member') {
    return (
      <div className="space-y-5">
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <span className="text-scurry-orange">🏢</span> Company Info
          </div>
          <p className="text-sm text-gray-500 mb-4">Your organization's details.</p>
          <div className="mb-3.5">
            <label className="block text-[13px] font-semibold text-gray-500 mb-1.5">Organization Name</label>
            <div className="px-3 py-2 border border-gray-100 rounded-lg text-sm bg-gray-50 text-gray-700">
              {user?.org?.name || '—'}
            </div>
          </div>
          <div>
            <label className="block text-[13px] font-semibold text-gray-500 mb-1.5">Domain</label>
            <div className="px-3 py-2 border border-gray-100 rounded-lg text-sm bg-gray-50 text-gray-700">
              {user?.org?.domain || '—'}
            </div>
          </div>
        </div>
      </div>
    )
  }

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
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="px-3.5 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors"
            >
              Delete Organization
            </button>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 bg-black/45 flex items-center justify-center z-50"
          onClick={() => setShowDeleteConfirm(false)}
        >
          <div
            className="bg-white rounded-xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[17px] font-bold text-red-600 mb-1">Delete Organization</div>
            <div className="text-sm text-gray-500 mb-4">
              This will permanently delete your organization, all workflows, sequences, team members,
              and billing data. This action <span className="font-bold text-red-600">cannot be undone</span>.
            </div>
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-800">
              All team members will lose access. Any active subscriptions will be cancelled.
            </div>
            <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
              Type <span className="font-mono text-red-600">delete my organization</span> to confirm
            </label>
            <input
              className="w-full px-3 py-2 border border-red-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-red-200 focus:border-red-400 mb-5"
              placeholder="delete my organization"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
            />
            <div className="flex gap-2.5">
              <button
                onClick={async () => {
                  setIsDeleting(true)
                  try {
                    await teamApi.deleteOrganization()
                    localStorage.removeItem('access_token')
                    localStorage.removeItem('refresh_token')
                    toast({ title: 'Organization deleted' })
                    navigate('/login')
                  } catch (err: any) {
                    setIsDeleting(false)
                    toast({
                      title: 'Error',
                      description: err.response?.data?.detail || 'Failed to delete organization',
                      variant: 'destructive',
                    })
                  }
                }}
                disabled={deleteConfirmText !== 'delete my organization' || isDeleting}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white text-sm font-semibold rounded-lg hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {isDeleting ? 'Deleting...' : 'Permanently Delete'}
              </button>
              <button
                onClick={() => {
                  setShowDeleteConfirm(false)
                  setDeleteConfirmText('')
                }}
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

export default SettingsOrganization
