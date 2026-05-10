import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Sparkles,
  Database,
} from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { RagTraceEntry } from '@/lib/api'

interface RagPanelProps {
  trace?: RagTraceEntry[] | null
}

const SKIP_REASON_LABELS: Record<string, { title: string; hint: string }> = {
  no_account_id: {
    title: 'No account_id on input data',
    hint: 'Workflow execution did not resolve a billing account. Check the owner→org→account chain.',
  },
  no_user_id: {
    title: 'No user_id on input data',
    hint: 'Workflow.owner_id is missing. Older workflows from before the org migration may need a backfill.',
  },
  openai_key_missing: {
    title: 'OPENAI_API_KEY not configured',
    hint: 'Embeddings cannot be generated. Set the env var and restart the backend.',
  },
  no_contact_match: {
    title: 'No contact matched the meeting participants',
    hint: 'Either this is a first meeting with everyone in the room, or every participant email is filtered as internal. Configure internal_domains and add the customer as a contact.',
  },
  contact_has_no_history: {
    title: 'Matched contact has no prior embeddings',
    hint: 'The contact exists, but no prior transcripts/emails are linked to them yet. After a few runs the briefing will start surfacing context.',
  },
  briefing_returned_empty: {
    title: 'Briefing query returned no relevant chunks',
    hint: 'Embeddings exist but none were similar enough to the current meeting. Check similarity_threshold or add more diverse historical data.',
  },
}

const SOURCE_TYPE_LABEL: Record<string, string> = {
  resource: 'Resource',
  text_gen_output: 'Text Gen Output',
  transcript_chunk: 'Transcript',
  generated_email: 'Past Email',
  activity: 'Contact Activity',
}

function formatDuration(ms: number): string {
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

function formatSimilarity(s: number | undefined): string {
  if (typeof s !== 'number' || Number.isNaN(s)) return '—'
  return s.toFixed(3)
}

interface CallSummary {
  totalCalls: number
  retrieveCalls: number
  totalChunks: number
  totalLatencyMs: number
  briefingFired: boolean
  emailContextFired: boolean
  presendFired: boolean
  skips: RagTraceEntry[]
  errors: RagTraceEntry[]
}

function summarize(entries: RagTraceEntry[]): CallSummary {
  let totalCalls = 0
  let retrieveCalls = 0
  let totalChunks = 0
  let totalLatencyMs = 0
  let briefingFired = false
  let emailContextFired = false
  let presendFired = false
  const skips: RagTraceEntry[] = []
  const errors: RagTraceEntry[] = []

  for (const e of entries) {
    if (e.type === 'rag.skip') {
      skips.push(e)
      continue
    }
    totalCalls += 1
    totalLatencyMs += e.duration_ms || 0
    if (e.error) errors.push(e)
    if (e.type === 'rag.retrieve_context') {
      retrieveCalls += 1
      const rc = e.response?.result_count
      if (typeof rc === 'number') totalChunks += rc
    }
    if (e.type === 'rag.get_contact_briefing') briefingFired = true
    if (e.type === 'rag.get_email_context') emailContextFired = true
    if (e.type === 'rag.get_presend_snapshot') presendFired = true
  }

  return {
    totalCalls,
    retrieveCalls,
    totalChunks,
    totalLatencyMs,
    briefingFired,
    emailContextFired,
    presendFired,
    skips,
    errors,
  }
}

function StatusBadge({ summary }: { summary: CallSummary }) {
  const ragRan = summary.totalCalls > 0
  const allSkipped = !ragRan && summary.skips.length > 0
  const noTrace = !ragRan && summary.skips.length === 0

  if (noTrace) {
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-gray-200 bg-gray-50">
        <Database className="h-4 w-4 text-gray-500 mt-0.5" />
        <div className="text-sm">
          <div className="font-medium text-gray-700">RAG not invoked</div>
          <div className="text-gray-500 text-xs">
            No RAG trace entries captured for this run.
          </div>
        </div>
      </div>
    )
  }

  if (allSkipped) {
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-yellow-200 bg-yellow-50">
        <AlertCircle className="h-4 w-4 text-yellow-700 mt-0.5" />
        <div className="text-sm">
          <div className="font-medium text-yellow-900">RAG skipped</div>
          <div className="text-yellow-800 text-xs">
            {summary.skips.length} skip event{summary.skips.length === 1 ? '' : 's'} —
            see Diagnostics below.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-green-200 bg-green-50">
      <Sparkles className="h-4 w-4 text-green-700 mt-0.5" />
      <div className="text-sm">
        <div className="font-medium text-green-900">RAG used</div>
        <div className="text-green-800 text-xs">
          {summary.totalCalls} call{summary.totalCalls === 1 ? '' : 's'} ·{' '}
          {summary.totalChunks} chunk{summary.totalChunks === 1 ? '' : 's'} retrieved ·{' '}
          {formatDuration(summary.totalLatencyMs)} total
        </div>
      </div>
    </div>
  )
}

function DiagnosticsList({ skips, errors }: { skips: RagTraceEntry[]; errors: RagTraceEntry[] }) {
  if (skips.length === 0 && errors.length === 0) return null
  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold text-gray-700 uppercase tracking-wide">
        Diagnostics
      </div>
      {skips.map((e) => {
        const reason = (e.response?.reason as string) || 'unknown'
        const label = SKIP_REASON_LABELS[reason] || {
          title: reason,
          hint: '',
        }
        const path = (e.metadata?.path as string) || ''
        return (
          <div
            key={e.id}
            className="flex items-start gap-2 px-3 py-2 rounded border border-yellow-200 bg-yellow-50 text-sm"
          >
            <AlertCircle className="h-4 w-4 text-yellow-700 mt-0.5 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="font-medium text-yellow-900">
                {label.title}
                {path && <span className="ml-2 text-xs text-yellow-700">({path})</span>}
              </div>
              {label.hint && (
                <div className="text-xs text-yellow-800 mt-0.5">{label.hint}</div>
              )}
              {e.metadata && Object.keys(e.metadata).length > 0 && (
                <details className="mt-1">
                  <summary className="cursor-pointer text-xs text-yellow-700 hover:underline">
                    Details
                  </summary>
                  <pre className="text-xs mt-1 bg-yellow-100 rounded p-2 overflow-x-auto">
                    {JSON.stringify(e.metadata, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          </div>
        )
      })}
      {errors.map((e) => (
        <div
          key={e.id}
          className="flex items-start gap-2 px-3 py-2 rounded border border-red-200 bg-red-50 text-sm"
        >
          <XCircle className="h-4 w-4 text-red-700 mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="font-medium text-red-900">{e.type} failed</div>
            <div className="text-xs text-red-800 mt-0.5 break-all">{e.error}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

function ChunkRow({ chunk }: { chunk: any }) {
  const sourceLabel = SOURCE_TYPE_LABEL[chunk.source_type] || chunk.source_type
  return (
    <div className="border-l-2 border-blue-200 pl-2 py-1">
      <div className="flex items-center gap-2 text-xs">
        <span className="font-mono text-blue-700">{sourceLabel}</span>
        <span className="text-gray-500">{chunk.source_id}</span>
        <span className="text-gray-400">·</span>
        <span className="text-gray-600">sim {formatSimilarity(chunk.similarity)}</span>
        {chunk._penalized && (
          <span className="text-xs text-orange-600">(penalized)</span>
        )}
      </div>
      {chunk.chunk_preview && (
        <div className="text-xs text-gray-700 mt-1 whitespace-pre-wrap break-words">
          {chunk.chunk_preview}
        </div>
      )}
    </div>
  )
}

function CallEntry({ entry }: { entry: RagTraceEntry }) {
  const [open, setOpen] = useState(false)
  const isError = !!entry.error
  const isSkip = entry.type === 'rag.skip'
  if (isSkip) return null // already rendered in DiagnosticsList

  // Header summary text varies by call type
  let headline = entry.type
  let detail = ''
  if (entry.type === 'rag.retrieve_context') {
    const rc = entry.response?.result_count ?? 0
    const total = entry.response?.results_total ?? rc
    headline = 'retrieve_context'
    detail = `${rc}${total !== rc ? `/${total}` : ''} chunk${rc === 1 ? '' : 's'}`
  } else if (entry.type === 'rag.get_email_context') {
    const blocks = entry.response?.blocks ?? []
    headline = 'get_email_context'
    detail = `${Array.isArray(blocks) ? blocks.length : 0} block${
      Array.isArray(blocks) && blocks.length === 1 ? '' : 's'
    } · ${entry.response?.formatted_chars ?? 0} chars`
  } else if (entry.type === 'rag.get_contact_briefing') {
    headline = 'get_contact_briefing'
    detail = entry.response?.briefing_chars
      ? `${entry.response.briefing_chars} chars`
      : 'no briefing produced'
  } else if (entry.type === 'rag.get_presend_snapshot') {
    headline = 'get_presend_snapshot'
    const verdict = entry.response?.verdict
    detail = verdict ? `verdict=${verdict}` : 'snapshot built'
  } else if (entry.type === 'openai.embeddings') {
    headline = 'openai.embeddings'
    const inputCount =
      entry.request?.input_count ?? entry.response?.input_count ?? '?'
    detail = `${inputCount} input${inputCount === 1 ? '' : 's'}`
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className={`w-full flex items-center gap-2 px-3 py-2 rounded text-left text-sm border ${
            isError
              ? 'border-red-200 bg-red-50 hover:bg-red-100'
              : 'border-gray-200 bg-gray-50 hover:bg-gray-100'
          }`}
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-gray-500" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-gray-500" />
          )}
          {isError ? (
            <XCircle className="h-3.5 w-3.5 text-red-600" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
          )}
          <span className="font-mono text-xs text-gray-800">{headline}</span>
          <span className="text-xs text-gray-600 flex-1">{detail}</span>
          <span className="text-xs text-gray-500">{formatDuration(entry.duration_ms)}</span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-6 pr-2 pt-2 pb-3 space-y-2">
        {entry.error && (
          <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2 break-all">
            {entry.error}
          </div>
        )}
        {entry.request && (
          <details>
            <summary className="cursor-pointer text-xs font-medium text-gray-700">
              Request
            </summary>
            <pre className="text-xs mt-1 bg-gray-100 rounded p-2 overflow-x-auto">
              {JSON.stringify(entry.request, null, 2)}
            </pre>
          </details>
        )}
        {entry.type === 'rag.retrieve_context' && Array.isArray(entry.response?.results) && (
          <div>
            <div className="text-xs font-medium text-gray-700 mb-1">
              Top chunks ({entry.response.results.length})
            </div>
            <div className="space-y-2">
              {entry.response.results.map((r: any, i: number) => (
                <ChunkRow key={`${r.id ?? i}-${r.chunk_index ?? i}`} chunk={r} />
              ))}
            </div>
          </div>
        )}
        {entry.response && entry.type !== 'rag.retrieve_context' && (
          <details>
            <summary className="cursor-pointer text-xs font-medium text-gray-700">
              Response
            </summary>
            <pre className="text-xs mt-1 bg-gray-100 rounded p-2 overflow-x-auto whitespace-pre-wrap break-words">
              {JSON.stringify(entry.response, null, 2)}
            </pre>
          </details>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}

export default function RagPanel({ trace }: RagPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const entries = Array.isArray(trace) ? trace : []
  const summary = summarize(entries)

  // Count of "interesting" call entries (not skip events, since they render
  // in Diagnostics instead).
  const callEntries = entries.filter((e) => e.type !== 'rag.skip')

  return (
    <div className="space-y-3">
      <StatusBadge summary={summary} />

      {(summary.skips.length > 0 || summary.errors.length > 0) && (
        <DiagnosticsList skips={summary.skips} errors={summary.errors} />
      )}

      {callEntries.length > 0 && (
        <Collapsible open={expanded} onOpenChange={setExpanded}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="w-full flex items-center gap-2 text-xs font-semibold text-gray-700 uppercase tracking-wide hover:text-gray-900"
            >
              {expanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
              RAG Calls ({callEntries.length})
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-1.5 pt-2">
            {callEntries.map((e) => (
              <CallEntry key={e.id} entry={e} />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
}
