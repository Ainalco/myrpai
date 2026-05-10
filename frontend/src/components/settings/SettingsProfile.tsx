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
