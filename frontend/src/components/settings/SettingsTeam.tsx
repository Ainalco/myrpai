import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { teamApi } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/components/ui/use-toast'
import { Loader2, Copy, Check, ChevronDown } from 'lucide-react'

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
  const [inviteLink, setInviteLink] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [roleMenuOpen, setRoleMenuOpen] = useState<number | null>(null)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [transferTarget, setTransferTarget] = useState<any>(null)
  const [removeTarget, setRemoveTarget] = useState<any>(null)

  const isAdmin = role === 'owner' || role === 'admin'

  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ['team-members'],
    queryFn: () => teamApi.listMembers().then((r) => r.data),
  })

  const { data: invitations } = useQuery({
    queryKey: ['team-invitations'],
    queryFn: () => teamApi.listInvitations().then((r) => r.data),
    enabled: isAdmin,
  })

  const inviteMutation = useMutation({
    mutationFn: (data: { email: string; role: string }) => teamApi.invite(data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['team-invitations'] })
      const link = `${window.location.origin}/accept-invite/${res.data.token}`
      setInviteLink(link)
      setInviteEmail('')
      toast({ title: 'Invitation created', description: `Invited ${res.data.email} as ${res.data.role}` })
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

  const changeRoleMutation = useMutation({
    mutationFn: ({ userId, newRole }: { userId: number; newRole: string }) =>
      teamApi.changeRole(userId, newRole),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      setRoleMenuOpen(null)
      toast({ title: 'Role updated', description: `Changed role to ${vars.newRole}` })
    },
    onError: (err: any) => {
      toast({
        title: 'Error',
        description: err.response?.data?.detail || 'Failed to change role',
        variant: 'destructive',
      })
    },
  })

  const transferMutation = useMutation({
    mutationFn: (userId: number) => teamApi.transferOwnership(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['team-members'] })
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
      setShowTransferModal(false)
      setTransferTarget(null)
      toast({ title: 'Ownership transferred', description: 'You are now an Admin.' })
    },
    onError: (err: any) => {
      toast({
        title: 'Error',
        description: err.response?.data?.detail || 'Failed to transfer ownership',
        variant: 'destructive',
      })
    },
  })

  const pendingInvitations = invitations?.filter((i: any) => i.status === 'pending') || []
  const getInitials = (name: string) =>
    name
      .split(' ')
      .map((n: string) => n[0])
      .join('')
      .toUpperCase()

  const copyToClipboard = async (text: string, id: string) => {
    await navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  // Determine what role options a member can be changed to
  const getRoleOptions = (member: any): string[] => {
    if (member.role === 'owner') return [] // Can't change owner's role
    if (member.id === user?.id) return [] // Can't change own role
    if (role === 'owner') {
      // Owner can set admin or member
      return member.role === 'admin' ? ['member'] : ['admin']
    }
    if (role === 'admin') {
      // Admin can only demote other admins to member
      if (member.role === 'admin') return ['member']
      return [] // Admin can't promote members
    }
    return []
  }

  if (!isAdmin) {
    // Read-only view for members
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="mb-4">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900">
            <span className="text-scurry-orange">👥</span> Your Team
          </div>
          <p className="text-sm text-gray-500">Members of your organization.</p>
        </div>
        {membersLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-scurry-orange" />
          </div>
        ) : (
          <div className="space-y-2.5">
            {members?.map((m: any) => {
              const badge = roleBadgeStyles[m.role] || roleBadgeStyles.member
              return (
                <div key={m.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-scurry-orange to-scurry-latte flex items-center justify-center text-[11px] text-white font-bold flex-shrink-0">
                    {getInitials(m.full_name || m.email)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">{m.full_name || m.email}</div>
                    <div className="text-xs text-gray-500">{m.email}</div>
                  </div>
                  <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${badge.classes}`}>
                    {badge.label}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    )
  }

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
            onClick={() => {
              setShowModal(true)
              setInviteLink(null)
            }}
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
                  const roleOptions = getRoleOptions(m)
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
                        {roleOptions.length > 0 ? (
                          <div className="relative">
                            <button
                              onClick={() => setRoleMenuOpen(roleMenuOpen === m.id ? null : m.id)}
                              className={`inline-flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full cursor-pointer hover:ring-2 hover:ring-scurry-orange/20 transition-all ${badge.classes}`}
                            >
                              {badge.label}
                              <ChevronDown className="w-3 h-3" />
                            </button>
                            {roleMenuOpen === m.id && (
                              <>
                                <div className="fixed inset-0 z-10" onClick={() => setRoleMenuOpen(null)} />
                                <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1 min-w-[140px]">
                                  {roleOptions.map((opt) => (
                                    <button
                                      key={opt}
                                      onClick={() => changeRoleMutation.mutate({ userId: m.id, newRole: opt })}
                                      className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
                                    >
                                      Change to <span className="font-semibold capitalize">{opt}</span>
                                    </button>
                                  ))}
                                  {role === 'owner' && m.role !== 'owner' && (
                                    <>
                                      <div className="border-t border-gray-100 my-1" />
                                      <button
                                        onClick={() => {
                                          setRoleMenuOpen(null)
                                          setTransferTarget(m)
                                          setShowTransferModal(true)
                                        }}
                                        className="w-full text-left px-3 py-2 text-sm text-amber-600 hover:bg-amber-50 transition-colors"
                                      >
                                        Transfer Ownership
                                      </button>
                                    </>
                                  )}
                                </div>
                              </>
                            )}
                          </div>
                        ) : (
                          <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${badge.classes}`}>
                            {badge.label}
                          </span>
                        )}
                      </td>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        {m.role !== 'owner' && m.id !== user?.id && (
                          !(role === 'admin' && m.role === 'admin') && (
                            <button
                              onClick={() => setRemoveTarget(m)}
                              className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 transition-colors"
                            >
                              Remove
                            </button>
                          )
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
          <p className="text-sm text-gray-500 mb-4">Invitations expire after 7 days. Share the invite link with the recipient.</p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  {['Email', 'Role', 'Invite Link', ''].map((h) => (
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
                {pendingInvitations.map((inv: any) => {
                  const linkId = `inv-${inv.id}`
                  return (
                    <tr key={inv.id}>
                      <td className="px-2.5 py-3 border-b border-gray-200">{inv.email}</td>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        <span className="text-[11px] font-bold text-gray-600 bg-gray-100 px-2 py-0.5 rounded-full capitalize">
                          {inv.role}
                        </span>
                      </td>
                      <td className="px-2.5 py-3 border-b border-gray-200">
                        {inv.token ? (
                          <button
                            onClick={() => copyToClipboard(`${window.location.origin}/accept-invite/${inv.token}`, linkId)}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-gray-50 border border-gray-200 rounded-md text-xs text-gray-600 hover:bg-gray-100 transition-colors"
                          >
                            {copiedId === linkId ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
                            {copiedId === linkId ? 'Copied!' : 'Copy Link'}
                          </button>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
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
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Transfer Ownership Modal */}
      {showTransferModal && transferTarget && (
        <div
          className="fixed inset-0 bg-black/45 flex items-center justify-center z-50"
          onClick={() => setShowTransferModal(false)}
        >
          <div
            className="bg-white rounded-xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[17px] font-bold mb-1 text-amber-600">Transfer Ownership</div>
            <div className="text-sm text-gray-500 mb-5">
              You are about to transfer ownership of this organization to{' '}
              <span className="font-semibold text-gray-900">{transferTarget.full_name || transferTarget.email}</span>.
              You will become an Admin.
            </div>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-5 text-sm text-amber-800">
              <span className="font-semibold">Warning:</span> This action transfers full control of the organization,
              including billing, team management, and all settings. This cannot be undone without the new owner's consent.
            </div>
            <div className="flex gap-2.5">
              <button
                onClick={() => transferMutation.mutate(transferTarget.id)}
                disabled={transferMutation.isPending}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-amber-500 text-white text-sm font-semibold rounded-lg hover:bg-amber-600 disabled:opacity-50 transition-colors"
              >
                {transferMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  'Transfer Ownership'
                )}
              </button>
              <button
                onClick={() => setShowTransferModal(false)}
                className="px-4 py-2 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Remove Member Modal */}
      {removeTarget && (
        <div
          className="fixed inset-0 bg-black/45 flex items-center justify-center z-50"
          onClick={() => setRemoveTarget(null)}
        >
          <div
            className="bg-white rounded-xl p-7 w-[440px] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[17px] font-bold text-red-600 mb-1">Remove Team Member</div>
            <div className="text-sm text-gray-500 mb-5">
              Are you sure you want to remove{' '}
              <span className="font-semibold text-gray-900">{removeTarget.full_name || removeTarget.email}</span>{' '}
              from the team? They will lose access to all organization resources.
            </div>
            <div className="flex gap-2.5">
              <button
                onClick={() => {
                  removeMutation.mutate(removeTarget.id)
                  setRemoveTarget(null)
                }}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white text-sm font-semibold rounded-lg hover:bg-red-700 transition-colors"
              >
                Remove Member
              </button>
              <button
                onClick={() => setRemoveTarget(null)}
                className="px-4 py-2 bg-white text-gray-900 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
            </div>
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
            {inviteLink ? (
              <>
                <div className="text-[17px] font-bold mb-1">Invitation Created</div>
                <div className="text-sm text-gray-500 mb-5">
                  Share this link with your team member. It expires in 7 days.
                </div>
                <div className="flex items-center gap-2 p-3 bg-gray-50 border border-gray-200 rounded-lg mb-5">
                  <input
                    className="flex-1 bg-transparent text-sm text-gray-700 outline-none truncate"
                    value={inviteLink}
                    readOnly
                    onClick={(e) => (e.target as HTMLInputElement).select()}
                  />
                  <button
                    onClick={() => copyToClipboard(inviteLink, 'invite-modal')}
                    className="flex-shrink-0 p-1.5 hover:bg-gray-200 rounded transition-colors"
                  >
                    {copiedId === 'invite-modal' ? (
                      <Check className="w-4 h-4 text-green-500" />
                    ) : (
                      <Copy className="w-4 h-4 text-gray-500" />
                    )}
                  </button>
                </div>
                <button
                  onClick={() => {
                    setShowModal(false)
                    setInviteLink(null)
                  }}
                  className="w-full px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover transition-colors"
                >
                  Done
                </button>
              </>
            ) : (
              <>
                <div className="text-[17px] font-bold mb-1">Invite a Team Member</div>
                <div className="text-sm text-gray-500 mb-5">
                  They'll receive an invite link valid for 7 days.
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
                  <option value="admin">Admin - can manage billing &amp; team</option>
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
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default SettingsTeam
