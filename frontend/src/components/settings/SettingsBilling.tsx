import React, { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { billingApi } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { Loader2 } from 'lucide-react'
import { AcornIcon } from '@/components/ui/acorn-icon'

declare global {
  interface Window {
    Paddle?: {
      Environment: { set: (env: string) => void }
      Initialize: (opts: { token: string }) => void
      Checkout: {
        open: (opts: {
          items: { priceId: string; quantity: number }[]
          customer?: { email?: string }
          customData?: Record<string, string>
          settings?: { displayMode?: string; successUrl?: string }
        }) => void
      }
    }
  }
}

const PLAN_PRICING: Record<string, { monthly: number; annual: number }> = {
  seedling: { monthly: 0, annual: 0 },
  oak: { monthly: 99, annual: 79 },
  redwood: { monthly: 249, annual: 199 },
}

const plans = [
  { key: 'seedling', name: 'Seedling', priceMonthly: 0, priceAnnual: 0, icon: '🌱', acorns: '100', free: true },
  { key: 'oak', name: 'Oak', priceMonthly: 99, priceAnnual: 79, icon: '🌳', popular: true, acorns: '375' },
  { key: 'redwood', name: 'Redwood', priceMonthly: 249, priceAnnual: 199, icon: '🌲', acorns: '800' },
  { key: 'ancient', name: 'Ancient Forest', priceMonthly: null, priceAnnual: null, icon: '🏔️', acorns: 'Custom' },
]

const TOPUP_OPTIONS = [
  { acorns: 500, label: 'Starter' },
  { acorns: 1750, label: 'Growth', popular: true },
  { acorns: 4000, label: 'Scale' },
]

const SettingsBilling: React.FC = () => {
  const { user, refreshAcorns } = useAuth()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const role = user?.role || 'member'

  const refreshBillingData = () => {
    refreshAcorns()
    queryClient.invalidateQueries({ queryKey: ['auth', 'me'] })
    queryClient.invalidateQueries({ queryKey: ['billing-status'] })
  }

  // Poll for plan changes after upgrade/downgrade/checkout
  const pollingRef = useRef<NodeJS.Timeout | null>(null)
  const pollingTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const expectedPlanRef = useRef<string | null>(null)
  const [pollingForChange, setPollingForChange] = useState(false)

  const startPollingForPlanChange = (expectedPlan?: string) => {
    stopPolling()
    if (expectedPlan) expectedPlanRef.current = expectedPlan
    setPollingForChange(true)

    pollingRef.current = setInterval(() => {
      refreshBillingData()
    }, 5000)

    // Stop after 2 minutes
    pollingTimeoutRef.current = setTimeout(() => {
      stopPolling()
    }, 120000)
  }

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
    if (pollingTimeoutRef.current) {
      clearTimeout(pollingTimeoutRef.current)
      pollingTimeoutRef.current = null
    }
    expectedPlanRef.current = null
    setPollingForChange(false)
  }

  const account = user?.account

  // Stop polling when the expected plan is detected
  useEffect(() => {
    if (!pollingForChange || !expectedPlanRef.current) return
    if (account?.plan_tier === expectedPlanRef.current) {
      const planName = expectedPlanRef.current.charAt(0).toUpperCase() + expectedPlanRef.current.slice(1)
      stopPolling()
      toast({ title: 'Plan Updated', description: `You're now on the ${planName} plan.` })
    }
  }, [account?.plan_tier, pollingForChange])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling()
  }, [])
  const currentPlan = account?.plan_tier || 'oak'
  const [paddleReady, setPaddleReady] = useState(false)
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'annual'>('monthly')
  const [cycleInitialized, setCycleInitialized] = useState(false)

  // Fetch billing status with full details
  const { data: billingStatus } = useQuery({
    queryKey: ['billing-status'],
    queryFn: () => billingApi.getStatus().then((r) => r.data),
    enabled: role !== 'member',
  })

  // Fetch Paddle price IDs and client token
  const { data: pricesData } = useQuery({
    queryKey: ['billing-prices'],
    queryFn: () => billingApi.getPrices().then((r) => r.data),
    enabled: role !== 'member',
  })

  // Sync billing cycle toggle with actual subscription cycle
  useEffect(() => {
    if (cycleInitialized) return
    const actual = billingStatus?.billing_cycle || account?.billing_cycle
    if (actual === 'annual') {
      setBillingCycle('annual')
      setCycleInitialized(true)
    } else if (actual) {
      setCycleInitialized(true)
    }
  }, [billingStatus, account, cycleInitialized])

  // Initialize Paddle.js
  useEffect(() => {
    if (!pricesData?.client_token) return

    // Load Paddle.js script if not already loaded
    if (!document.querySelector('script[src*="paddle.com"]')) {
      const script = document.createElement('script')
      script.src = 'https://cdn.paddle.com/paddle/v2/paddle.js'
      script.async = true
      script.onload = () => {
        if (window.Paddle) {
          window.Paddle.Environment.set(pricesData.environment || 'sandbox')
          window.Paddle.Initialize({ token: pricesData.client_token })
          setPaddleReady(true)
        }
      }
      document.head.appendChild(script)
    } else if (window.Paddle) {
      setPaddleReady(true)
    }
  }, [pricesData])

  const openCheckout = (priceId: string) => {
    if (!window.Paddle || !paddleReady) {
      toast({
        title: 'Error',
        description: 'Payment system is loading. Please try again.',
        variant: 'destructive',
      })
      return
    }
    if (!priceId) {
      toast({
        title: 'Error',
        description: 'This plan is not available for purchase yet.',
        variant: 'destructive',
      })
      return
    }

    window.Paddle.Checkout.open({
      items: [{ priceId, quantity: 1 }],
      customer: { email: user?.email || '' },
      customData: { user_id: String(user?.id || '') },
      settings: {
        displayMode: 'overlay',
        successUrl: window.location.href + '?checkout=success',
      },
    })
  }

  const [upgrading, setUpgrading] = useState(false)
  const [showUpgradeModal, setShowUpgradeModal] = useState(false)
  const [upgradeToPlan, setUpgradeToPlan] = useState('')

  const handlePlanUpgrade = (planKey: string) => {
    if (planKey === 'ancient') {
      toast({ title: 'Contact Us', description: 'Please reach out for custom Enterprise pricing.' })
      return
    }
    setUpgradeToPlan(planKey)
    setShowUpgradeModal(true)
  }

  const confirmUpgrade = async () => {
    setUpgrading(true)
    setShowUpgradeModal(false)
    try {
      const res = await billingApi.upgrade(upgradeToPlan, billingCycle)
      const data = res.data

      if (data.action === 'checkout') {
        if (data.price_id) {
          openCheckout(data.price_id)
          startPollingForPlanChange(upgradeToPlan)
        } else {
          toast({
            title: 'Unavailable',
            description: 'This plan is not configured for checkout yet.',
            variant: 'destructive',
          })
        }
      } else if (data.action === 'upgraded') {
        startPollingForPlanChange(upgradeToPlan)
      }
    } catch (error: any) {
      toast({
        title: 'Upgrade Failed',
        description: error.response?.data?.detail || 'Failed to upgrade plan. Please try again.',
        variant: 'destructive',
      })
    } finally {
      setUpgrading(false)
    }
  }

  const upgradePlanInfo = plans.find((p) => p.key === upgradeToPlan)
  const upgradePrice = upgradePlanInfo
    ? billingCycle === 'annual'
      ? upgradePlanInfo.priceAnnual
      : upgradePlanInfo.priceMonthly
    : 0

  const handleBuyAcorns = (acorns: number) => {
    // Find the matching topup price ID
    const topups = pricesData?.topups || {}
    const entry = Object.entries(topups).find(([, amt]) => amt === acorns)
    if (!entry) {
      toast({
        title: 'Unavailable',
        description: 'This top-up option is not configured yet.',
        variant: 'destructive',
      })
      return
    }
    openCheckout(entry[0])
  }

  const [cancelling, setCancelling] = useState(false)

  // --- Flow 1: Cancellation modal (Paid → Seedling) ---
  const [showCancelModal, setShowCancelModal] = useState(false)
  const [cancelStep, setCancelStep] = useState(0)
  const [cancelReasons, setCancelReasons] = useState<Record<string, string>>({})
  const [cancelOtherText, setCancelOtherText] = useState('')

  const cancelQuestions = [
    {
      id: 'reason',
      question: "We're sad to see you go! What's the main reason you're downgrading?",
      options: [
        'Too expensive for my current needs',
        'Not generating enough sequences to justify the cost',
        "Sequence quality didn't meet expectations",
        'Switched to a different tool',
        'My team/company needs changed',
        "Just taking a break — I'll be back",
        'Other',
      ],
      allowOther: true,
    },
    {
      id: 'retention',
      question: 'Would you be open to hearing about a special offer to keep your current plan?',
      options: [
        "Yes, I'd consider the right offer",
        "No thanks, I've made my decision",
      ],
    },
  ]

  const openCancelModal = () => {
    setCancelStep(0)
    setCancelReasons({})
    setCancelOtherText('')
    setShowCancelModal(true)
  }

  const handleCancelConfirm = async () => {
    setCancelling(true)
    try {
      const res = await billingApi.cancel()
      toast({
        title: 'Subscription Cancelled',
        description: res.data.message || "You'll keep access until the end of your billing period.",
      })
      setShowCancelModal(false)
      refreshAcorns()
    } catch (error: any) {
      toast({
        title: 'Cancel Failed',
        description: error.response?.data?.detail || 'Failed to cancel subscription.',
        variant: 'destructive',
      })
    } finally {
      setCancelling(false)
    }
  }

  // --- Flow 2: Tier downgrade modal (Redwood → Oak) ---
  const [showDowngradeModal, setShowDowngradeModal] = useState(false)
  const [downgradeTo, setDowngradeTo] = useState('')
  const [downgradeReason, setDowngradeReason] = useState('')
  const [downgradeOtherText, setDowngradeOtherText] = useState('')

  const downgradeOptions = [
    "Don't need the extra Acorns",
    "Don't use the advanced features",
    'Reducing costs',
    'Other',
  ]

  const openDowngradeModal = (planKey: string) => {
    setDowngradeTo(planKey)
    setDowngradeReason('')
    setDowngradeOtherText('')
    setShowDowngradeModal(true)
  }

  const handleDowngradeConfirm = async () => {
    setUpgrading(true)
    try {
      const res = await billingApi.upgrade(downgradeTo, billingCycle)
      const data = res.data
      if (data.action === 'checkout' && data.price_id) {
        openCheckout(data.price_id)
        startPollingForPlanChange(downgradeTo)
      } else if (data.action === 'upgraded') {
        startPollingForPlanChange(downgradeTo)
      }
      setShowDowngradeModal(false)
    } catch (error: any) {
      toast({
        title: 'Downgrade Failed',
        description: error.response?.data?.detail || 'Failed to change plan.',
        variant: 'destructive',
      })
    } finally {
      setUpgrading(false)
    }
  }

  const periodEndDate = account?.current_period_ends_at
    ? new Date(account.current_period_ends_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : 'the end of your billing period'

  // Check for successful checkout return
  useEffect(() => {
    if (window.location.search.includes('checkout=success')) {
      toast({ title: 'Payment Successful', description: 'Updating your plan...' })
      startPollingForPlanChange()
      // Clean URL
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  if (role === 'member') {
    return (
      <div className="bg-white border border-gray-200 rounded-[10px] p-12 text-center">
        <div className="text-4xl mb-3">💰</div>
        <div className="text-[15px] font-bold text-gray-900 mb-1.5">The Treasury Vault</div>
        <div className="text-sm text-gray-500 max-w-sm mx-auto">
          Nice try, but the treasury vault has a squirrel-proof lock! Only Owners and Admins can count the nuts in here. Your Acorns are safe, we promise.
        </div>
      </div>
    )
  }

  const status = billingStatus?.status || account?.status || 'trialing'
  const cycle = billingStatus?.billing_cycle || account?.billing_cycle || 'monthly'
  const acornBalance = billingStatus
    ? billingStatus.acorn_balance
    : account
      ? account.acorn_balance
      : 0

  const statusLabel: Record<string, { text: string; classes: string }> = {
    active: { text: 'Active', classes: 'text-green-700 bg-green-50' },
    trialing: { text: 'Trial', classes: 'text-scurry-orange bg-scurry-orange-light' },
    past_due: { text: 'Past Due', classes: 'text-red-600 bg-red-50' },
    cancelled: { text: 'Cancelled', classes: 'text-gray-600 bg-gray-100' },
    suspended: { text: 'Suspended', classes: 'text-red-600 bg-red-50' },
  }

  const currentStatus = statusLabel[status] || statusLabel.active

  return (
    <div className="space-y-5">
      {/* Polling indicator */}
      {pollingForChange && (
        <div className="bg-scurry-orange-light border border-orange-200 rounded-lg p-3 flex items-center gap-2 text-sm text-scurry-orange font-medium">
          <Loader2 className="w-4 h-4 animate-spin" />
          Updating your plan — this may take a few seconds...
        </div>
      )}

      {/* Current Plan */}
      <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900">
            <span className="text-scurry-orange">📋</span> Current Plan
          </div>
          <span
            className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full ${currentStatus.classes}`}
          >
            {currentStatus.text}
          </span>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Manage your subscription and upgrade or downgrade at any time.
        </p>

        {/* Billing cycle toggle */}
        <div className="flex items-center gap-2 mb-4">
          <button
            onClick={() => setBillingCycle('monthly')}
            className={`px-3 py-1 rounded-lg text-xs font-bold border transition-colors ${
              billingCycle === 'monthly'
                ? 'bg-scurry-orange text-white border-scurry-orange'
                : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
            }`}
          >
            Monthly
          </button>
          <button
            onClick={() => setBillingCycle('annual')}
            className={`px-3 py-1 rounded-lg text-xs font-bold border transition-colors ${
              billingCycle === 'annual'
                ? 'bg-scurry-orange text-white border-scurry-orange'
                : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
            }`}
          >
            Annual
            <span className="ml-1 text-[9px] opacity-80">Save 20%</span>
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {plans.map((p) => {
            const isCurrent = p.key === currentPlan && status !== 'trialing'
            const planOrder = ['seedling', 'oak', 'redwood', 'ancient']
            const currentIdx = planOrder.indexOf(currentPlan)
            const thisIdx = planOrder.indexOf(p.key)
            const isDowngrade = thisIdx < currentIdx && status !== 'trialing'

            const getButtonLabel = () => {
              if (p.priceMonthly == null) return 'Contact Us'
              if (p.free) return isDowngrade ? 'Downgrade to Free' : 'Select'
              return isDowngrade ? 'Downgrade' : 'Upgrade'
            }

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
                {status === 'trialing' && p.key === 'redwood' && (
                  <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-scurry-orange text-white text-[9px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap">
                    TRIAL ACTIVE
                  </div>
                )}
                <div className="text-[22px] mb-1">{p.icon}</div>
                <div className="font-bold text-sm mb-0.5">{p.name}</div>
                <div className="text-xl font-extrabold text-scurry-orange">
                  {p.free
                    ? 'Free'
                    : p.priceMonthly != null
                      ? `$${billingCycle === 'annual' ? p.priceAnnual : p.priceMonthly}`
                      : 'Custom'}
                </div>
                {!p.free && p.priceMonthly != null && (
                  <div className="text-[11px] text-gray-500">
                    /user/{billingCycle === 'annual' ? 'mo (billed yearly)' : 'mo'}
                  </div>
                )}
                <div className="text-[11px] text-gray-400 mt-0.5">{p.acorns} acorns/mo</div>
                {!isCurrent && (
                  <button
                    onClick={() => {
                      if (p.free) {
                        openCancelModal()
                      } else if (isDowngrade) {
                        openDowngradeModal(p.key)
                      } else {
                        handlePlanUpgrade(p.key)
                      }
                    }}
                    disabled={upgrading || cancelling || (p.free && currentPlan === 'seedling' && status !== 'trialing')}
                    className="mt-2.5 w-full py-1.5 px-2.5 bg-white text-gray-900 border border-gray-200 rounded-lg text-[11px] font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors inline-flex items-center justify-center gap-1"
                  >
                    {(upgrading || cancelling) ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      getButtonLabel()
                    )}
                  </button>
                )}
              </div>
            )
          })}
        </div>

        {status === 'trialing' ? (
          <div className="mt-3 text-xs text-gray-400">
            You're on a <span className="font-semibold text-scurry-orange">free trial</span> with full Redwood access
          </div>
        ) : currentPlan !== 'seedling' && cycle ? (
          <div className="mt-3 text-xs text-gray-400">
            Currently on <span className="font-semibold text-gray-600 capitalize">{currentPlan}</span> — <span className="capitalize">{cycle}</span> billing
          </div>
        ) : null}
      </div>

      {/* Acorn Balance + Subscription Info */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Acorn Balance */}
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-1">
            <AcornIcon className="w-4 h-4" /> Acorn Balance
          </div>
          <div className="text-4xl font-extrabold text-scurry-orange my-1.5">
            {Math.round(acornBalance).toLocaleString()}
          </div>
          <div className="text-sm text-gray-500 mb-3.5">Acorns remaining — never expire</div>

          {/* Top-up buttons — paid plans only */}
          {currentPlan !== 'seedling' && status !== 'trialing' ? (
          <div className="space-y-2 mb-3.5">
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
              Buy More Acorns
            </div>
            <div className="grid grid-cols-3 gap-2">
              {TOPUP_OPTIONS.map((opt) => (
                <button
                  key={opt.acorns}
                  onClick={() => handleBuyAcorns(opt.acorns)}
                  disabled={!paddleReady}
                  className={`relative p-2.5 rounded-lg border text-center transition-all hover:shadow-sm disabled:opacity-50 ${
                    opt.popular
                      ? 'border-scurry-orange bg-scurry-orange-light/30 hover:border-scurry-orange-hover'
                      : 'border-gray-200 hover:border-scurry-orange'
                  }`}
                >
                  {opt.popular && (
                    <span className="absolute -top-2 left-1/2 -translate-x-1/2 bg-scurry-orange text-white text-[8px] px-1.5 py-0.5 rounded-full font-bold">
                      POPULAR
                    </span>
                  )}
                  <div className="text-sm font-bold text-gray-900">
                    {opt.acorns.toLocaleString()}
                  </div>
                  <div className="text-[10px] text-gray-500">{opt.label}</div>
                </button>
              ))}
            </div>
          </div>
          ) : (
          <div className="text-xs text-gray-400 bg-gray-50 border border-gray-200 rounded-lg p-3 mb-3.5">
            Top-up packs are only available on paid plans. Upgrade to Oak or Redwood to buy more Acorns.
            {currentPlan === 'seedling' && (
              <span className="block mt-1 text-amber-600 font-medium">
                Seedling accounts are capped at 300 Acorns.
              </span>
            )}
          </div>
          )}

          {!paddleReady && pricesData?.client_token && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              Loading payment system...
            </div>
          )}
        </div>

        {/* Subscription Details */}
        <div className="bg-white border border-gray-200 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center gap-2 text-[15px] font-bold text-gray-900 mb-3">
            <span className="text-scurry-orange">📊</span> Subscription Details
          </div>

          <div className="space-y-3">
            <div className="flex justify-between items-center py-2 border-b border-gray-100">
              <span className="text-sm text-gray-500">Plan</span>
              <span className="text-sm font-semibold capitalize">{currentPlan}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-100">
              <span className="text-sm text-gray-500">Status</span>
              <span
                className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${currentStatus.classes}`}
              >
                {currentStatus.text}
              </span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-100">
              <span className="text-sm text-gray-500">Billing Cycle</span>
              <span className="text-sm font-semibold capitalize">{cycle || '—'}</span>
            </div>
            {account?.current_period_ends_at && (
              <div className="flex justify-between items-center py-2 border-b border-gray-100">
                <span className="text-sm text-gray-500">Next Billing</span>
                <span className="text-sm font-semibold">
                  {new Date(account.current_period_ends_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </span>
              </div>
            )}
            {status === 'trialing' && account?.trial_ends_at && (
              <div className="flex justify-between items-center py-2 border-b border-gray-100">
                <span className="text-sm text-gray-500">Trial Ends</span>
                <span className="text-sm font-semibold">
                  {new Date(account.trial_ends_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </span>
              </div>
            )}
            {status === 'cancelled' && account?.current_period_ends_at && (
              <div className="flex justify-between items-center py-2 border-b border-gray-100">
                <span className="text-sm text-red-500 font-medium">Downgrades to Free</span>
                <span className="text-sm font-semibold text-red-600">
                  {new Date(account.current_period_ends_at).toLocaleDateString('en-US', {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                  })}
                </span>
              </div>
            )}
            {PLAN_PRICING[currentPlan] && (
              <div className="flex justify-between items-center py-2 border-b border-gray-100">
                <span className="text-sm text-gray-500">Price</span>
                <span className="text-sm font-semibold">
                  {PLAN_PRICING[currentPlan].monthly === 0
                    ? 'Free'
                    : cycle === 'annual'
                      ? `$${PLAN_PRICING[currentPlan].annual}/mo (billed yearly at $${PLAN_PRICING[currentPlan].annual * 12}/yr)`
                      : `$${PLAN_PRICING[currentPlan].monthly}/mo`}
                </span>
              </div>
            )}
            {PLAN_PRICING[currentPlan] && PLAN_PRICING[currentPlan].monthly > 0 && (
              <div className="flex justify-between items-center py-2">
                <span className="text-sm text-gray-500">Acorns/mo</span>
                <span className="text-sm font-semibold">
                  {plans.find((p) => p.key === currentPlan)?.acorns || '—'}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Cancel Subscription — only show for active paid subscribers */}
      {status === 'active' && currentPlan !== 'seedling' && currentPlan !== 'trialing' && (
        <div className="bg-white border border-red-300 rounded-[10px] p-5 sm:p-6">
          <div className="flex items-center justify-between p-4 bg-red-50 rounded-lg">
            <div>
              <div className="font-semibold text-sm">Cancel Subscription</div>
              <div className="text-xs text-gray-500 mt-0.5">
                You'll keep access until the end of your billing period, then move to the free Seedling plan.
              </div>
            </div>
            <button
              onClick={openCancelModal}
              disabled={cancelling}
              className="px-3.5 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-semibold hover:bg-red-100 disabled:opacity-50 transition-colors inline-flex items-center gap-1"
            >
              {cancelling ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Cancel Plan'}
            </button>
          </div>
        </div>
      )}

      {/* ── Flow 1: Cancellation Modal (Paid → Seedling) ── */}
      {showCancelModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowCancelModal(false)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-[480px] shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-red-50 px-6 py-4 border-b border-red-100">
              <div className="text-base font-bold text-gray-900">Cancel your subscription?</div>
              <div className="text-sm text-gray-500 mt-0.5">We hate to see a fellow squirrel leave the tree.</div>
            </div>

            <div className="px-6 py-5">
              {cancelStep < cancelQuestions.length ? (
                <>
                  <div className="mb-1 text-xs text-gray-400 font-medium">
                    Question {cancelStep + 1} of {cancelQuestions.length}
                  </div>
                  <div className="text-sm font-semibold text-gray-900 mb-3">
                    {cancelQuestions[cancelStep].question}
                  </div>
                  <div className="space-y-2 mb-3">
                    {cancelQuestions[cancelStep].options.map((opt) => {
                      const qId = cancelQuestions[cancelStep].id
                      const selected = cancelReasons[qId] === opt
                      return (
                        <button
                          key={opt}
                          onClick={() => setCancelReasons((prev) => ({ ...prev, [qId]: opt }))}
                          className={`w-full text-left px-3.5 py-2.5 rounded-lg border text-sm transition-all ${
                            selected
                              ? 'border-scurry-orange bg-scurry-orange-light font-medium'
                              : 'border-gray-200 hover:bg-gray-50'
                          }`}
                        >
                          {opt}
                        </button>
                      )
                    })}
                  </div>
                  {/* "Other" free text box */}
                  {cancelQuestions[cancelStep].allowOther && cancelReasons[cancelQuestions[cancelStep].id] === 'Other' && (
                    <textarea
                      value={cancelOtherText}
                      onChange={(e) => setCancelOtherText(e.target.value)}
                      placeholder="Tell us more..."
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm mb-3 resize-none h-20 focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
                    />
                  )}
                  <div className="flex gap-2.5 mt-2">
                    <button
                      onClick={() => setCancelStep((s) => s + 1)}
                      disabled={
                        !cancelReasons[cancelQuestions[cancelStep].id] ||
                        (cancelQuestions[cancelStep].allowOther &&
                          cancelReasons[cancelQuestions[cancelStep].id] === 'Other' &&
                          !cancelOtherText.trim())
                      }
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-gray-900 text-white text-sm font-semibold rounded-lg hover:bg-gray-800 disabled:opacity-40 transition-colors"
                    >
                      {cancelStep < cancelQuestions.length - 1 ? 'Next' : 'Continue'}
                    </button>
                    <button
                      onClick={() => setShowCancelModal(false)}
                      className="px-4 py-2 bg-white text-gray-700 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                    >
                      Never mind, keep my plan
                    </button>
                  </div>
                </>
              ) : (
                <>
                  {/* Acorn warning */}
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-4">
                    <div className="flex gap-2.5">
                      <span className="text-base mt-0.5">⚠️</span>
                      <div className="text-sm text-amber-900 leading-relaxed">
                        <p className="font-semibold mb-2">Before you go — here's what happens on Seedling:</p>
                        <p className="mb-2">
                          Seedling accounts can hold up to <strong>300 Acorns</strong>. You've currently got{' '}
                          <strong className="text-scurry-orange">{Math.round(acornBalance).toLocaleString()}</strong>.
                          {acornBalance > 300 && (
                            <> Any Acorns above 300 will be <strong>released back into the wild</strong> on <strong>{periodEndDate}</strong>.</>
                          )}
                        </p>
                        <p className="mb-2">
                          Paid plans? <strong>No stash limit — ever.</strong>
                        </p>
                        <p>
                          Top-up packs are also <strong>only available on paid plans</strong> — so once you're on Seedling,
                          what you've got is what you've got (plus your monthly 100).
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 mb-5 text-sm text-gray-600">
                    You'll keep <strong className="text-gray-900">{currentPlan.charAt(0).toUpperCase() + currentPlan.slice(1)}</strong> access
                    until <strong className="text-gray-900">{periodEndDate}</strong>, then
                    you'll be moved to the free Seedling plan.
                  </div>

                  <div className="flex gap-2.5">
                    <button
                      onClick={handleCancelConfirm}
                      disabled={cancelling}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-600 text-white text-sm font-semibold rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
                    >
                      {cancelling ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Yes, cancel my subscription'}
                    </button>
                    <button
                      onClick={() => setShowCancelModal(false)}
                      className="px-4 py-2 bg-scurry-orange text-white rounded-lg text-sm font-semibold hover:bg-scurry-orange-hover transition-colors"
                    >
                      Keep my plan
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Upgrade Confirmation Modal ── */}
      {showUpgradeModal && upgradePlanInfo && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowUpgradeModal(false)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-[420px] shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-scurry-orange-light px-6 py-4 border-b border-orange-200">
              <div className="text-base font-bold text-gray-900">
                Upgrade to {upgradePlanInfo.name}?
              </div>
            </div>

            <div className="px-6 py-5">
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">New plan</span>
                  <span className="font-semibold">{upgradePlanInfo.name}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Billing</span>
                  <span className="font-semibold capitalize">{billingCycle}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Price</span>
                  <span className="font-semibold text-scurry-orange">
                    ${upgradePrice}/{billingCycle === 'annual' ? 'mo (billed yearly)' : 'mo'}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Acorns</span>
                  <span className="font-semibold">{upgradePlanInfo.acorns}/mo</span>
                </div>
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-5 text-sm text-amber-800 flex gap-2">
                <span>💳</span>
                <span>
                  {status === 'trialing'
                    ? 'Your trial will end and your card will be charged immediately.'
                    : currentPlan === 'seedling'
                      ? 'Your card will be charged immediately upon confirming.'
                      : 'Your current plan will be updated and your card will be charged the prorated difference immediately.'}
                </span>
              </div>

              <div className="flex gap-2.5">
                <button
                  onClick={confirmUpgrade}
                  disabled={upgrading}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
                >
                  {upgrading ? <Loader2 className="w-4 h-4 animate-spin" /> : `Upgrade to ${upgradePlanInfo.name}`}
                </button>
                <button
                  onClick={() => setShowUpgradeModal(false)}
                  className="px-4 py-2 bg-white text-gray-700 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Flow 2: Tier Downgrade Modal (Redwood → Oak) ── */}
      {showDowngradeModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowDowngradeModal(false)}
        >
          <div
            className="bg-white rounded-xl w-full max-w-[480px] shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="bg-amber-50 px-6 py-4 border-b border-amber-100">
              <div className="text-base font-bold text-gray-900">
                Switch to {downgradeTo.charAt(0).toUpperCase() + downgradeTo.slice(1)}?
              </div>
              <div className="text-sm text-gray-500 mt-0.5">
                No problem — mind sharing why it's a better fit?
              </div>
            </div>

            <div className="px-6 py-5">
              <div className="text-sm font-semibold text-gray-900 mb-3">
                What's the main reason for switching?
              </div>
              <div className="space-y-2 mb-3">
                {downgradeOptions.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setDowngradeReason(opt)}
                    className={`w-full text-left px-3.5 py-2.5 rounded-lg border text-sm transition-all ${
                      downgradeReason === opt
                        ? 'border-scurry-orange bg-scurry-orange-light font-medium'
                        : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
              {downgradeReason === 'Other' && (
                <textarea
                  value={downgradeOtherText}
                  onChange={(e) => setDowngradeOtherText(e.target.value)}
                  placeholder="Tell us more..."
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm mb-3 resize-none h-20 focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
                />
              )}
              <div className="flex gap-2.5 mt-2">
                <button
                  onClick={handleDowngradeConfirm}
                  disabled={
                    upgrading ||
                    !downgradeReason ||
                    (downgradeReason === 'Other' && !downgradeOtherText.trim())
                  }
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-scurry-orange text-white text-sm font-semibold rounded-lg hover:bg-scurry-orange-hover disabled:opacity-50 transition-colors"
                >
                  {upgrading ? <Loader2 className="w-4 h-4 animate-spin" /> : `Switch to ${downgradeTo.charAt(0).toUpperCase() + downgradeTo.slice(1)}`}
                </button>
                <button
                  onClick={() => setShowDowngradeModal(false)}
                  className="px-4 py-2 bg-white text-gray-700 border border-gray-200 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors"
                >
                  Keep current plan
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default SettingsBilling
