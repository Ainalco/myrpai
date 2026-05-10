import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { workflowApi, FreshCheckSettings, RagSettings } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/components/ui/use-toast'
import { Loader2, ShieldCheck, Lock, Lightbulb } from 'lucide-react'

interface Props {
    workflowId: number
    ragSettings?: RagSettings
}

// Collapse rapid toggle spam into a single PUT. Short enough that the user
// perceives the save as immediate, long enough that 5 clicks in a row fire
// once. The mutation also runs with `disabled={isPending}` so overlapping
// requests can't reorder on the wire.
const SAVE_DEBOUNCE_MS = 300

// Plan tiers that unlock the Pulse rule (rule 4). Keep aligned with the
// Account.plan_tier enum in backend/models.py.
const OAK_PLUS_TIERS = new Set(['oak', 'redwood', 'ancient_forest'])

// Rules 1–7 — togglable. Rule 8 (DNC) is rendered separately, locked-on.
// `planGated` means the toggle is disabled on non-Oak+ plans; the stored
// value is still persisted so the toggle re-enables cleanly when the
// account upgrades.
// `isNew` flags the three rules added with the Fresh Check / RAG Point C
// upgrade so the UI can mark them visually until users get used to them.
type FreshCheckRule = {
    id: keyof FreshCheckSettings
    label: string
    planGated?: boolean
    isNew?: boolean
}

const FRESH_CHECK_RULES: FreshCheckRule[] = [
    {
        id: 'reply_received',
        label: 'Contact replied to any Scurry email across all your workflows',
    },
    {
        id: 'inbox_email',
        label: 'Contact sent a manual email or replied from your inbox since queue time',
    },
    {
        id: 'activity_logged',
        label: 'A meeting, call, or logged activity happened with this contact',
    },
    {
        id: 'pulse_shift',
        label: 'Contact’s Pulse turned negative or flagged as disengaged',
        planGated: true,
        isNew: true,
    },
    {
        id: 'org_signal',
        label: 'Someone else at the same organization signaled “not interested”',
        isNew: true,
    },
    {
        id: 'crm_change',
        label: 'CRM deal stage changed to Lost, Won, or Paused',
        isNew: true,
    },
    {
        id: 'flagged_note',
        label: 'A user note flags the deal as dead, objection raised, or request to stop',
    },
]

const deriveSettings = (ragSettings?: RagSettings): RagSettings => ({
    smart_context_diversity: ragSettings?.smart_context_diversity !== false,
    thin_transcript_prompt: ragSettings?.thin_transcript_prompt !== false,
    fresh_check: deriveFreshCheck(ragSettings?.fresh_check),
})

const deriveFreshCheck = (fc?: FreshCheckSettings): FreshCheckSettings => ({
    // Missing toggles default to TRUE (FreshCheckSettings defaults in
    // backend/workflows.py). Use `!== false` rather than `?? true` so an
    // explicit `false` from the server is preserved.
    reply_received: fc?.reply_received !== false,
    inbox_email: fc?.inbox_email !== false,
    activity_logged: fc?.activity_logged !== false,
    pulse_shift: fc?.pulse_shift !== false,
    org_signal: fc?.org_signal !== false,
    crm_change: fc?.crm_change !== false,
    flagged_note: fc?.flagged_note !== false,
})

const RagSettingsPanel: React.FC<Props> = ({ workflowId, ragSettings }) => {
    const queryClient = useQueryClient()
    const { toast } = useToast()
    const { user } = useAuth()

    const isOakPlus = useMemo(() => {
        const tier = user?.account?.plan_tier
        return tier ? OAK_PLUS_TIERS.has(tier) : false
    }, [user?.account?.plan_tier])

    const [localSettings, setLocalSettings] = useState<RagSettings>(
        deriveSettings(ragSettings)
    )

    const mutation = useMutation({
        mutationFn: (data: RagSettings) =>
            workflowApi.update(workflowId, {
                rag_settings: data,
            }),

        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
            toast({ title: 'Success', description: 'Context settings saved' })
        },
        onError: (error: any) => {
            toast({
                title: 'Error',
                description:
                    error?.response?.data?.detail ||
                    error?.message ||
                    'Failed to save context settings',
                variant: 'destructive',
            })
        },
    })

    // Re-sync from props only when no save is in flight or queued, so stale
    // props can't clobber a toggle the user just flipped.
    const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
    const pendingPayloadRef = useRef<RagSettings | null>(null)

    useEffect(() => {
        if (!mutation.isPending && saveTimerRef.current === null) {
            setLocalSettings(deriveSettings(ragSettings))
        }
    }, [ragSettings, mutation.isPending])

    // Flush or cancel any outstanding debounce on unmount. We fire the last
    // buffered payload on the way out so a toggle the user just clicked is
    // still persisted even if they navigate away before the 300ms elapses.
    useEffect(() => {
        return () => {
            if (saveTimerRef.current !== null) {
                clearTimeout(saveTimerRef.current)
                saveTimerRef.current = null
                if (pendingPayloadRef.current) {
                    mutation.mutate(pendingPayloadRef.current)
                    pendingPayloadRef.current = null
                }
            }
        }
        // Intentionally empty dep array — this cleanup must run on unmount only,
        // not every render (which would cancel every in-flight debounce).
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    const scheduleSave = (updated: RagSettings) => {
        setLocalSettings(updated)
        pendingPayloadRef.current = updated

        if (saveTimerRef.current !== null) {
            clearTimeout(saveTimerRef.current)
        }
        saveTimerRef.current = setTimeout(() => {
            saveTimerRef.current = null
            const payload = pendingPayloadRef.current
            pendingPayloadRef.current = null
            if (payload) {
                mutation.mutate(payload)
            }
        }, SAVE_DEBOUNCE_MS)
    }

    const handleTopLevelUpdate = (
        field: 'smart_context_diversity' | 'thin_transcript_prompt',
        value: boolean,
    ) => {
        scheduleSave({ ...localSettings, [field]: value })
    }

    const handleFreshCheckUpdate = (
        field: keyof FreshCheckSettings,
        value: boolean,
    ) => {
        scheduleSave({
            ...localSettings,
            fresh_check: {
                ...(localSettings.fresh_check ?? {}),
                [field]: value,
            },
        })
    }

    const currentFreshCheck = localSettings.fresh_check ?? {}

    return (
    <div className="bg-white border border-scurry-gray-border rounded-lg p-5 space-y-6">

      {/* Header */}
      <div>
        <h3 className="text-lg font-semibold text-scurry-espresso">
          Context Settings
        </h3>
        <p className="text-sm text-scurry-latte">
          Control how the timeline, organization-wide activity, and
          connected CRM data are woven into each email.
        </p>
      </div>

      {/* Smart Context Diversity */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <Label
            htmlFor="smartContextDiversitySwitch"
            className="text-sm font-medium text-scurry-espresso"
          >
            Smart Context Diversity
          </Label>
          <p className="text-xs text-scurry-latte mt-1">
            When ON, chunks already used earlier in a sequence are penalized
            so later emails pull fresh context. Turn OFF for short sequences
            where continuity matters more than novelty.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {mutation.isPending && (
            <Loader2 className="h-4 w-4 animate-spin text-scurry-orange" />
          )}

          <Switch
            id="smartContextDiversitySwitch"
            checked={localSettings.smart_context_diversity !== false}
            disabled={mutation.isPending}
            onCheckedChange={(val) =>
              handleTopLevelUpdate('smart_context_diversity', val)
            }
          />
        </div>
      </div>

      {/* Thin Transcript Prompt */}
      <div className="flex items-start justify-between gap-4 pt-4 border-t border-scurry-gray-border">
        <div>
          <Label
            htmlFor="thinTranscriptPromptSwitch"
            className="text-sm font-medium text-scurry-espresso"
          >
            Thin Transcript Prompt
          </Label>
          <p className="text-xs text-scurry-latte mt-1">
            When on, workflows on sparse transcripts (2+ Tier-1 fields missing)
            automatically pull a wider window of contact history and
            organization-wide activity. Turn off for workflows designed
            to run on minimal input.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {mutation.isPending && (
            <Loader2 className="h-4 w-4 animate-spin text-scurry-orange" />
          )}

          <Switch
            id="thinTranscriptPromptSwitch"
            checked={localSettings.thin_transcript_prompt !== false}
            disabled={mutation.isPending}
            onCheckedChange={(val) =>
              handleTopLevelUpdate('thin_transcript_prompt', val)
            }
          />
        </div>
      </div>

      {/* Fresh Check — 7 togglable rules + locked DNC */}
      <div className="pt-4 border-t border-scurry-gray-border space-y-4">
        <div className="flex items-start gap-3">
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-scurry-espresso flex items-center gap-2">
              <span aria-hidden>🐿️</span>
              Fresh Check
            </h4>
            <p className="text-xs text-scurry-latte mt-1">
              Before each send, reads the contact’s timeline, organization-wide
              activity, connected CRM, and your other workflows. Toggle any
              check below off if it doesn’t fit your workflow.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5 mt-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-green-600" />
            Enabled
          </span>
        </div>

        <div className="rounded-md border border-amber-200 bg-amber-50/60 px-4 py-3 space-y-1">
          <p className="text-xs font-semibold text-scurry-espresso mb-1">
            The AI will STOP sending this email if:
          </p>

          {FRESH_CHECK_RULES.map((rule) => {
            const enabled = currentFreshCheck[rule.id] !== false
            const isPlanDisabled = rule.planGated === true && !isOakPlus

            return (
              <div
                key={rule.id}
                className={
                  'flex items-center justify-between gap-3 py-1.5 ' +
                  (isPlanDisabled ? 'opacity-60' : '')
                }
              >
                <Label
                  htmlFor={`freshCheck-${rule.id}`}
                  className={
                    'text-xs flex-1 leading-snug flex items-center flex-wrap gap-x-1.5 gap-y-0.5 ' +
                    (enabled
                      ? 'text-scurry-espresso'
                      : 'text-scurry-latte')
                  }
                >
                  <span>{rule.label}</span>
                  {rule.isNew && (
                    <span className="text-[10px] font-bold tracking-wide text-white bg-green-600 rounded px-1.5 py-0.5">
                      NEW
                    </span>
                  )}
                  {isPlanDisabled && (
                    <span
                      className="text-[10px] font-semibold text-scurry-orange bg-scurry-orange/10 rounded px-1.5 py-0.5"
                      title="Upgrade to Oak or higher to enable the Pulse rule"
                    >
                      Oak+
                    </span>
                  )}
                </Label>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {mutation.isPending && (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-scurry-orange" />
                  )}
                  <Switch
                    id={`freshCheck-${rule.id}`}
                    checked={enabled}
                    disabled={mutation.isPending || isPlanDisabled}
                    onCheckedChange={(val) =>
                      handleFreshCheckUpdate(rule.id, val)
                    }
                  />
                </div>
              </div>
            )
          })}

          {/* DNC rule — locked ON, non-interactive */}
          <div className="flex items-center justify-between gap-3 py-1.5 mt-1 rounded-md bg-green-50/60 border border-green-200/60 px-3">
            <div className="flex-1">
              <div className="flex items-center gap-1.5 text-xs text-scurry-espresso leading-snug">
                <ShieldCheck className="h-3.5 w-3.5 text-scurry-orange flex-shrink-0" />
                <span>Contact or organization marked as Do Not Contact</span>
              </div>
              <div className="text-[11px] text-scurry-latte mt-0.5 flex items-center gap-1">
                <Lock className="h-3 w-3" />
                Always on — core safety, can’t be turned off
              </div>
            </div>
            <Switch checked disabled />
          </div>
        </div>

        {/* When Fresh Check stops an email — explanation panel */}
        <div>
          <p className="text-xs font-semibold text-scurry-espresso mb-1.5">
            When Fresh Check stops an email:
          </p>
          <div className="rounded-md border border-amber-200 bg-amber-50/60 px-4 py-3 space-y-1.5">
            <p className="text-xs font-semibold text-scurry-orange">
              AI picks the right action based on context:
            </p>
            <ul className="space-y-1 text-xs text-scurry-espresso leading-snug">
              <li className="flex gap-2">
                <span className="text-scurry-orange font-bold flex-shrink-0">
                  →
                </span>
                <span>
                  <strong>Cancel the sequence</strong> — clear kill signals
                  (DNC, deal lost, “stop emailing me”)
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-scurry-orange font-bold flex-shrink-0">
                  →
                </span>
                <span>
                  <strong>Cancel this email only</strong> — this specific email
                  is now irrelevant
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-scurry-orange font-bold flex-shrink-0">
                  →
                </span>
                <span>
                  <strong>Skip this email, continue</strong> — minor context
                  shift, later emails still make sense
                </span>
              </li>
              <li className="flex gap-2">
                <span className="text-scurry-orange font-bold flex-shrink-0">
                  →
                </span>
                <span>
                  <strong>Reschedule for later</strong> — temporary blocker. AI
                  picks the date from context (vacation reply → return date,
                  “try next quarter” → 60 days)
                </span>
              </li>
            </ul>
            <p className="text-[11px] text-scurry-latte pt-1.5 mt-1.5 border-t border-dashed border-amber-300">
              Every decision is logged with reasoning in your queue. Override
              anytime in review.
            </p>
          </div>
        </div>

        {/* Smart skip note */}
        <div className="flex items-start gap-2 text-[11px] text-scurry-latte leading-snug">
          <Lightbulb className="h-3.5 w-3.5 text-scurry-burst flex-shrink-0 mt-0.5" />
          <span>
            <strong className="text-scurry-espresso">Smart skip:</strong> If
            nothing has changed in the contact’s context since this email was
            queued, Fresh Check skips the AI call entirely and sends. Most
            sends hit this path — the AI only runs when there’s something
            worth evaluating.
          </span>
        </div>

        {/* AI Filter pointer */}
        <div className="pt-2 border-t border-scurry-gray-border text-[11px] text-scurry-latte leading-snug">
          Need custom AI checks (intent scoring, deal size filters, etc.)? Use{' '}
          <strong className="text-scurry-orange">AI Filter</strong> on this
          workflow instead — it’s built for that.
        </div>
      </div>

      {/* Status hint */}
      {mutation.isPending && (
        <p className="text-xs text-scurry-latte">
          Saving changes...
        </p>
      )}
    </div>
  )
}

export default RagSettingsPanel
