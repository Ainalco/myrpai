import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiKeyApi, ApiKeyInfo, authApi, gmailApiService, outlookApiService, twilioApi, whatsappApi } from '@/lib/api'
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
          className={`flex items-start gap-2 p-3 rounded-lg mb-3.5 text-sm ${testResult.success
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

const TwilioIntegrationCard: React.FC = () => {
  const [accountSid, setAccountSid] = useState('')
  const [authToken, setAuthToken] = useState('')
  const [fromNumber, setFromNumber] = useState('')
  const [showToken, setShowToken] = useState(false)
  const { toast } = useToast()

  const saveMutation = useMutation({
    mutationFn: () =>
      twilioApi.saveSettings({
        account_sid: accountSid,
        auth_token: authToken,
        from_number: fromNumber,
      }),
    onSuccess: () => {
      toast({ title: 'Success', description: 'Twilio settings saved successfully' })
      setAccountSid('')
      setAuthToken('')
      setFromNumber('')
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save Twilio settings',
        variant: 'destructive',
      })
    },
  })

  return (
    <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-scurry-orange text-base">📱</span>
        <span className="font-bold text-[15px]">Twilio SMS</span>
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Connect your own Twilio account to send SMS follow-ups through Scurry.
      </p>

      <div className="space-y-3.5">
        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            Account SID
          </label>
          <input
            type="text"
            value={accountSid}
            onChange={(e) => setAccountSid(e.target.value)}
            placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          />
        </div>

        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            Auth Token
          </label>
          <div className="relative">
            <input
              type={showToken ? 'text' : 'password'}
              value={authToken}
              onChange={(e) => setAuthToken(e.target.value)}
              placeholder="Enter your Twilio auth token"
              className="w-full px-3 py-2 pr-9 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
            />
            <button
              onClick={() => setShowToken(!showToken)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
              type="button"
            >
              {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            From Phone Number
          </label>
          <input
            type="text"
            value={fromNumber}
            onChange={(e) => setFromNumber(e.target.value)}
            placeholder="+15551234567"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          />
        </div>
      </div>

      <button
        onClick={() => saveMutation.mutate()}
        disabled={saveMutation.isPending || !accountSid.trim() || !authToken.trim() || !fromNumber.trim()}
        className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
      >
        {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save Twilio Settings'}
      </button>
    </div>
  )
}

const WhatsAppIntegrationCard: React.FC = () => {
  const [phoneNumberId, setPhoneNumberId] = useState('')
  const [businessAccountId, setBusinessAccountId] = useState('')
  const [accessToken, setAccessToken] = useState('')
  const [webhookVerifyToken, setWebhookVerifyToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const { toast } = useToast()

  const saveMutation = useMutation({
    mutationFn: () =>
      whatsappApi.saveSettings({
        phone_number_id: phoneNumberId,
        business_account_id: businessAccountId || undefined,
        access_token: accessToken,
        webhook_verify_token: webhookVerifyToken,
      }),
    onSuccess: () => {
      toast({ title: 'Success', description: 'WhatsApp settings saved successfully' })
      setPhoneNumberId('')
      setBusinessAccountId('')
      setAccessToken('')
      setWebhookVerifyToken('')
    },
    onError: (error: any) => {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save WhatsApp settings',
        variant: 'destructive',
      })
    },
  })

  return (
    <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-scurry-orange text-base">💬</span>
        <span className="font-bold text-[15px]">WhatsApp Business</span>
      </div>

      <p className="text-sm text-gray-500 mb-4">
        Connect WhatsApp Business Cloud API to send approved WhatsApp follow-ups.
      </p>

      <div className="space-y-3.5">
        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            Phone Number ID
          </label>
          <input
            type="text"
            value={phoneNumberId}
            onChange={(e) => setPhoneNumberId(e.target.value)}
            placeholder="Meta Phone Number ID"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          />
        </div>

        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            Business Account ID
          </label>
          <input
            type="text"
            value={businessAccountId}
            onChange={(e) => setBusinessAccountId(e.target.value)}
            placeholder="WhatsApp Business Account ID"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          />
        </div>

        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            Access Token
          </label>
          <div className="relative">
            <input
              type={showToken ? 'text' : 'password'}
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              placeholder="Meta access token"
              className="w-full px-3 py-2 pr-9 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
            />
            <button
              onClick={() => setShowToken(!showToken)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
              type="button"
            >
              {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-[13px] font-semibold text-gray-900 mb-1.5">
            Webhook Verify Token
          </label>
          <input
            type="text"
            value={webhookVerifyToken}
            onChange={(e) => setWebhookVerifyToken(e.target.value)}
            placeholder="A private verify token you also set in backend env"
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
          />
        </div>
      </div>

      <button
        onClick={() => saveMutation.mutate()}
        disabled={
          saveMutation.isPending ||
          !phoneNumberId.trim() ||
          !accessToken.trim() ||
          !webhookVerifyToken.trim()
        }
        className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
      >
        {saveMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Save WhatsApp Settings'}
      </button>

      <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
        Meta webhook URL should point to your backend route:
        <div className="font-mono text-xs mt-1">
          https://your-backend-domain.com/whatsapp/webhook
        </div>
      </div>
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
          onRefresh={() => { }}
        />
      ))}
      <TwilioIntegrationCard />
      <WhatsAppIntegrationCard />

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
