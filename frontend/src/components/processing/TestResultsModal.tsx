import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Play,
  Download,
  RefreshCw,
  Activity,
  ChevronRight,
  ChevronDown,
  Copy,
  Loader2
} from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { useToast } from '@/components/ui/use-toast'
import { executionApi, type Execution, type ComponentExecution } from '@/lib/api'
import { formatExecutionTime, formatRelativeTime } from '@/lib/utils'
import RagPanel from '@/components/processing/RagPanel'

interface TestResultsModalProps {
  open: boolean
  onClose: () => void
  workflowId: number
}

type ExecutionStep = ComponentExecution

// ─── Component type icon/color mapping ───────────────────────────

const COMPONENT_STYLE: Record<string, { icon: string; bg: string }> = {
  input_sources:     { icon: '📥', bg: 'bg-blue-50' },
  text_generation:   { icon: '🤖', bg: 'bg-orange-50' },
  ai_filter:         { icon: '🧠', bg: 'bg-purple-50' },
  email:             { icon: '📧', bg: 'bg-green-50' },
  conditional_logic: { icon: '🔀', bg: 'bg-yellow-50' },
  action:            { icon: '⚡', bg: 'bg-cyan-50' },
}
const DEFAULT_STYLE = { icon: '📦', bg: 'bg-gray-50' }

const AI_COMPONENT_TYPES = ['text_generation', 'ai_filter']

// ─── Status helpers ──────────────────────────────────────────────

const STATUS_CONFIG = {
  completed: { color: 'text-scurry-green', border: 'border-l-scurry-green', bg: 'bg-green-50', label: '✓ DONE', dot: 'bg-scurry-green' },
  failed:    { color: 'text-scurry-red', border: 'border-l-scurry-red', bg: 'bg-red-50', label: '✗ FAILED', dot: 'bg-scurry-red' },
  running:   { color: 'text-scurry-energy-burst', border: 'border-l-scurry-energy-burst', bg: 'bg-yellow-50', label: '⟳ RUNNING', dot: 'bg-scurry-energy-burst' },
  pending:   { color: 'text-scurry-gray-muted', border: 'border-l-scurry-gray-border', bg: 'bg-gray-50', label: '○ PENDING', dot: 'bg-scurry-gray-border' },
} as const

function getStatusConfig(status: string) {
  return STATUS_CONFIG[status as keyof typeof STATUS_CONFIG] || STATUS_CONFIG.pending
}

// ─── Smart Data Renderers ────────────────────────────────────────

function sanitizeData(data: any): any {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return data
  return Object.fromEntries(
    Object.entries(data).filter(([key]) => !HIDDEN_FIELDS.has(key))
  )
}

function SmartDataDisplay({ data, componentType }: { data: any; componentType: string }) {
  const [showRaw, setShowRaw] = useState(false)
  const { toast } = useToast()
  const safeData = sanitizeData(data)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(safeData, null, 2))
      toast({ title: 'Copied!', description: 'Output data copied to clipboard' })
    } catch {
      toast({ title: 'Copy failed', description: 'Could not access clipboard', variant: 'destructive' })
    }
  }

  const isAI = AI_COMPONENT_TYPES.includes(componentType)
  const sectionLabel = isAI ? 'AI Output' : 'Output'

  return (
    <div className="pt-3 border-t border-gray-100">
      {/* Section label */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[10px] uppercase tracking-wider text-scurry-orange font-bold">{sectionLabel}</span>
        <div className="flex-1 h-px bg-gray-100" />
      </div>

      {/* Content */}
      {showRaw ? (
        <pre className="bg-scurry-gray-light rounded-lg p-3 text-xs font-mono max-h-[200px] overflow-y-auto text-scurry-espresso whitespace-pre-wrap">
          {JSON.stringify(safeData, null, 2)}
        </pre>
      ) : isAI ? (
        <AIOutputDisplay data={safeData} />
      ) : (
        <MiniCardsGrid data={safeData} />
      )}

      {/* Action buttons */}
      <div className="flex gap-2 mt-3">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-[11px] bg-scurry-gray-light px-3 py-1.5 rounded-md text-scurry-gray-secondary hover:bg-scurry-gray-border transition-colors"
        >
          <Copy className="h-3 w-3" /> Copy
        </button>
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="flex items-center gap-1.5 text-[11px] bg-scurry-gray-light px-3 py-1.5 rounded-md text-scurry-gray-secondary hover:bg-scurry-gray-border transition-colors"
        >
          {'{ }'} {showRaw ? 'Smart' : 'Raw'}
        </button>
      </div>
    </div>
  )
}

// Fields that should never be shown to users
const HIDDEN_FIELDS = new Set(['model_used', 'ai_model', 'model_id', 'model'])

function MiniCardsGrid({ data }: { data: any }) {
  if (!data || typeof data !== 'object') return null

  // Flatten: if data has a single wrapper key like "status"/"output", look deeper
  const entries = Object.entries(data).filter(([key]) => !HIDDEN_FIELDS.has(key)).flatMap(([key, value]) => {
    if (typeof value === 'object' && value !== null && !Array.isArray(value) && Object.keys(data).length <= 2) {
      // If there's a nested object and parent has few keys, flatten one level
      return Object.entries(value as Record<string, any>).map(([k, v]) => [k, v] as [string, any])
    }
    return [[key, value]] as [string, any][]
  })

  return (
    <div className="grid grid-cols-2 gap-2">
      {entries.map(([key, value]) => (
        <div key={key} className="bg-scurry-gray-light rounded-lg p-3 border border-gray-100">
          <div className="text-[9px] uppercase tracking-wider text-scurry-gray-muted font-semibold mb-1">
            {key.replace(/_/g, ' ')}
          </div>
          <div className="text-[13px] text-scurry-espresso font-medium break-words">
            {formatValue(value)}
          </div>
        </div>
      ))}
    </div>
  )
}

function formatValue(value: any): string {
  if (value === null || value === undefined) return '—'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return String(value)
}

function AIOutputDisplay({ data }: { data: any }) {
  // Extract the text content from the output data
  let text = ''
  if (typeof data === 'string') {
    text = data
  } else if (data?.output) {
    text = typeof data.output === 'string' ? data.output : JSON.stringify(data.output)
  } else if (data?.result) {
    text = typeof data.result === 'string' ? data.result : JSON.stringify(data.result)
  } else if (data?.text) {
    text = typeof data.text === 'string' ? data.text : JSON.stringify(data.text)
  } else if (data?.summary) {
    text = typeof data.summary === 'string' ? data.summary : JSON.stringify(data.summary)
  } else {
    // Fallback: render as mini cards if we can't find a text field
    return <MiniCardsGrid data={data} />
  }

  return (
    <div className="bg-[#FFF8F5] border border-scurry-orange/10 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm">🤖</span>
        <span className="text-[11px] text-scurry-orange font-semibold">AI Generated</span>
      </div>
      <div className="text-[13px] text-scurry-espresso leading-relaxed whitespace-pre-wrap">
        {text}
      </div>
    </div>
  )
}

// ─── Progress Timeline ───────────────────────────────────────────

function ProgressTimeline({ steps }: { steps: ExecutionStep[] }) {
  if (!steps.length) return null

  return (
    <div className="mb-5 px-5">
      <div className="flex items-start">
        {steps.map((step, i) => {
          const config = getStatusConfig(step.status)
          const isLast = i === steps.length - 1
          const isPending = step.status === 'pending'
          return (
            <React.Fragment key={step.component_id}>
              <div className="flex flex-col items-center gap-1 flex-shrink-0" style={{ minWidth: 60 }}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                  isPending ? 'border-2 border-scurry-gray-border bg-white' : `${config.dot} text-white`
                }`}>
                  {step.status === 'completed' ? '✓' :
                   step.status === 'failed' ? '✗' :
                   step.status === 'running' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> :
                   <span className="text-scurry-gray-muted text-[10px]">○</span>}
                </div>
                <div className={`text-[9px] font-semibold whitespace-nowrap ${config.color}`}>
                  {step.execution_time ? formatExecutionTime(step.execution_time) : '—'}
                </div>
                <div className="text-[10px] text-scurry-latte text-center max-w-[70px] truncate">
                  {step.component_name}
                </div>
              </div>
              {!isLast && (
                <div className={`flex-1 h-[3px] mx-[-2px] mt-[13px] ${
                  step.status === 'completed' ? 'bg-scurry-green' : 'bg-scurry-gray-border'
                }`} />
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}

// ─── Step Card ───────────────────────────────────────────────────

function StepCardControlled({ step }: { step: ExecutionStep }) {
  const [isOpen, setIsOpen] = useState(false)
  const style = COMPONENT_STYLE[step.component_type] || DEFAULT_STYLE
  const config = getStatusConfig(step.status)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className={`border border-scurry-gray-border rounded-xl overflow-hidden bg-white border-l-4 ${config.border}`}>
        <CollapsibleTrigger className="w-full">
          <div className="flex items-center gap-3 p-3.5 cursor-pointer hover:bg-gray-50/50 transition-colors">
            <div className={`w-8 h-8 rounded-lg ${style.bg} flex items-center justify-center text-sm`}>
              {style.icon}
            </div>
            <div className="flex-1 text-left">
              <div className="font-semibold text-sm text-scurry-espresso">{step.component_name}</div>
              <div className="text-[11px] text-scurry-gray-muted">
                {step.component_type.replace(/_/g, ' ')}
                {step.execution_time ? ` · ${formatExecutionTime(step.execution_time)}` : ''}
              </div>
            </div>
            <span className={`text-[10px] font-semibold ${config.color}`}>
              {config.label}
            </span>
            {isOpen
              ? <ChevronDown className="h-4 w-4 text-scurry-gray-muted" />
              : <ChevronRight className="h-4 w-4 text-scurry-gray-muted" />
            }
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-4 pb-4">
            {step.error_message && (
              <div className="bg-scurry-red-light border border-scurry-red/15 rounded-lg p-3 flex gap-2">
                <AlertTriangle className="h-4 w-4 text-scurry-red flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-xs font-semibold text-red-700 mb-0.5">Error</div>
                  <div className="text-xs text-red-600">{step.error_message}</div>
                </div>
              </div>
            )}
            {step.output_data && !step.error_message && (
              <SmartDataDisplay data={step.output_data} componentType={step.component_type} />
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ─── Live Elapsed Timer ──────────────────────────────────────────

function formatElapsed(startedAt: string): string {
  const diff = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
  return diff < 60 ? `${diff}s` : `${Math.floor(diff / 60)}m ${diff % 60}s`
}

function ElapsedTimer({ startedAt }: { startedAt: string }) {
  const [elapsed, setElapsed] = useState(() => formatElapsed(startedAt))

  useEffect(() => {
    const id = setInterval(() => setElapsed(formatElapsed(startedAt)), 1000)
    return () => clearInterval(id)
  }, [startedAt])

  return <span>Running — {elapsed} elapsed</span>
}

// ─── Main Modal ──────────────────────────────────────────────────

const TestResultsModal: React.FC<TestResultsModalProps> = ({
  open,
  onClose,
  workflowId
}) => {
  const { data: latestExecution, isLoading, refetch } = useQuery({
    queryKey: ['latest-execution', workflowId],
    queryFn: async () => {
      const result = await executionApi.getLatest(workflowId)
      return result
    },
    enabled: open && !!workflowId,
    refetchInterval: (query) => {
      const status = query.state?.data?.data?.status
      return status === 'running' || status === 'pending' ? 2000 : false
    }
  })

  const execution: Execution | undefined = latestExecution?.data

  const exportResults = () => {
    if (!execution) return
    // Strip hidden fields from component execution output_data before export
    const sanitized = {
      ...execution,
      component_executions: execution.component_executions.map(ce => ({
        ...ce,
        output_data: ce.output_data ? sanitizeData(ce.output_data) : ce.output_data,
      }))
    }
    const dataStr = JSON.stringify(sanitized, null, 2)
    const dataBlob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(dataBlob)
    const link = document.createElement('a')
    link.href = url
    link.download = `execution-${execution.id}-results.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const steps = execution?.component_executions || []
  const completedCount = steps.filter(s => s.status === 'completed').length
  const statusConfig = execution ? getStatusConfig(execution.status) : null
  const isRunning = execution?.status === 'running' || execution?.status === 'pending'

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col p-0">
        {/* Header */}
        <DialogHeader className="px-6 py-4 border-b border-scurry-gray-border">
          <div className="flex items-center justify-between">
            <DialogTitle className="font-display text-scurry-espresso">Test Results</DialogTitle>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
                <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
              {execution && (
                <Button variant="outline" size="sm" onClick={exportResults}>
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Body */}
        <div className="overflow-y-auto flex-1 min-h-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <LoadingSpinner size="lg" />
            </div>
          ) : !execution ? (
            <div className="text-center py-16">
              <Activity className="h-12 w-12 text-scurry-gray-muted mx-auto mb-4" />
              <h3 className="text-lg font-medium text-scurry-espresso mb-2">No Test Results</h3>
              <p className="text-scurry-latte mb-4">Run a test to see execution results and performance metrics.</p>
              <Button onClick={onClose}>
                <Play className="h-4 w-4 mr-2" />
                Run Test
              </Button>
            </div>
          ) : (
            <div className="p-6 space-y-5">

              {/* ── Hero Stats Banner ── */}
              <div className={`bg-white rounded-xl p-5 border border-scurry-gray-border border-l-4 border-l-scurry-orange ${
                isRunning ? 'animate-pulse [animation-duration:3s]' : ''
              }`}>
                {/* Top row: status */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-full ${statusConfig!.bg} flex items-center justify-center`}>
                      {execution.status === 'completed' ? (
                        <CheckCircle className="h-5 w-5 text-scurry-green" />
                      ) : execution.status === 'failed' ? (
                        <XCircle className="h-5 w-5 text-scurry-red" />
                      ) : execution.status === 'running' ? (
                        <Loader2 className="h-5 w-5 text-scurry-energy-burst animate-spin" />
                      ) : (
                        <Clock className="h-5 w-5 text-scurry-gray-muted" />
                      )}
                    </div>
                    <div>
                      <div className="font-bold text-base text-scurry-espresso">Execution #{execution.id}</div>
                      <div className="text-xs text-scurry-latte">
                        {isRunning
                          ? <ElapsedTimer startedAt={execution.started_at} />
                          : execution.status === 'failed'
                          ? `Failed ${formatRelativeTime(new Date(execution.started_at))}`
                          : `Completed ${formatRelativeTime(new Date(execution.started_at))}`
                        }
                      </div>
                    </div>
                  </div>
                  <div className={`px-3 py-1 rounded-full text-xs font-semibold ${
                    execution.status === 'completed' ? 'bg-green-50 text-scurry-green' :
                    execution.status === 'failed' ? 'bg-red-50 text-scurry-red' :
                    execution.status === 'running' ? 'bg-yellow-50 text-scurry-energy-burst' :
                    'bg-gray-50 text-scurry-gray-muted'
                  }`}>
                    <span className="relative inline-flex h-2 w-2 mr-1.5">
                      {isRunning && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75" />}
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-current" />
                    </span>
                    {execution.status.charAt(0).toUpperCase() + execution.status.slice(1)}
                  </div>
                </div>

                {/* Metric cards */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-scurry-gray-light rounded-lg p-3 text-center">
                    <div className="text-xl font-bold text-scurry-orange">
                      {execution.total_execution_time
                        ? formatExecutionTime(execution.total_execution_time)
                        : '—'
                      }
                    </div>
                    <div className="text-[10px] text-scurry-latte uppercase tracking-wider mt-0.5">Duration</div>
                  </div>
                  <div className="bg-scurry-gray-light rounded-lg p-3 text-center">
                    <div className="text-xl font-bold text-scurry-orange">
                      {completedCount}/{steps.length}
                    </div>
                    <div className="text-[10px] text-scurry-latte uppercase tracking-wider mt-0.5">Steps</div>
                  </div>
                  <div className="bg-scurry-gray-light rounded-lg p-3 text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      <span className="text-xl font-bold text-scurry-orange">
                        {execution.acorns_used != null ? Math.round(execution.acorns_used) : '—'}
                      </span>
                      <img src="/favicon.svg" alt="acorn" className="w-5 h-5" />
                    </div>
                    <div className="text-[10px] text-scurry-latte uppercase tracking-wider mt-0.5">Acorns Used</div>
                  </div>
                </div>

                {/* Execution-level error */}
                {execution.error_message && (
                  <div className="mt-4 bg-scurry-red-light border border-scurry-red/15 rounded-lg p-3 flex gap-2">
                    <AlertTriangle className="h-4 w-4 text-scurry-red flex-shrink-0 mt-0.5" />
                    <div>
                      <div className="text-xs font-semibold text-red-700 mb-0.5">Execution Error</div>
                      <div className="text-xs text-red-600">{execution.error_message}</div>
                    </div>
                  </div>
                )}
              </div>

              {/* ── Progress Timeline ── */}
              <ProgressTimeline steps={steps} />

              {/* ── RAG Activity ── */}
              <div className="bg-white rounded-xl p-5 border border-scurry-gray-border">
                <h3 className="text-sm font-semibold text-scurry-espresso mb-3 flex items-center">
                  <Activity className="h-4 w-4 mr-2" />
                  RAG Activity
                </h3>
                <RagPanel trace={execution.rag_trace} />
              </div>

              {/* ── Step Cards ── */}
              <div className="space-y-2.5">
                {steps.map((step) => (
                  <StepCardControlled key={step.component_id} step={step} />
                ))}
              </div>

            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default TestResultsModal
