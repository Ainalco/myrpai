import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AxiosError } from 'axios'
import {
  Database,
  Zap,
  Layers,
  Clock,
  AlertTriangle,
} from 'lucide-react'
import { adminApi } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import LoadingSpinner from '@/components/ui/loading-spinner'

function formatRelativeTime(timestamp: number): string {
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

function MetricCardSkeleton() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-4 rounded-full" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-9 w-24 mb-2" />
        <Skeleton className="h-3 w-40" />
      </CardContent>
    </Card>
  )
}

export default function AdminRAGPage() {
  const {
    data: metrics,
    isLoading,
    isFetching,
    error,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['admin', 'rag-metrics'],
    queryFn: () => adminApi.getRagMetrics().then((r) => r.data),
    refetchInterval: 60000, // refresh every 60s to match cache TTL
  })

  // Tick once per second so the "last updated" label stays fresh.
  const [, setNow] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setNow((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const Header = (
    <>
      <div className="mb-6">
        <Link to="/admin" className="text-sm text-muted-foreground hover:underline">
          &larr; Back to Admin
        </Link>
      </div>
      <div className="flex flex-row items-center gap-3 mb-2">
        <h1 className="text-2xl font-bold">RAG Observability</h1>
        {isFetching && !isLoading && (
          <span
            className="flex items-center gap-1 text-xs text-muted-foreground"
            aria-live="polite"
          >
            <LoadingSpinner size="sm" />
            Refreshing…
          </span>
        )}
      </div>
      <p className="text-muted-foreground mb-1">
        Monitor RAG embeddings, cache performance, and retrieval latency.
      </p>
      {dataUpdatedAt > 0 && (
        <p className="text-xs text-muted-foreground mb-6" aria-live="polite">
          Last updated {formatRelativeTime(dataUpdatedAt)}
        </p>
      )}
    </>
  )

  if (isLoading) {
    return (
      <div className="p-6">
        {Header}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <MetricCardSkeleton key={i} />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    const status = (error as AxiosError)?.response?.status
    let message: string
    if (status === 403) {
      message = 'You do not have admin access to view RAG metrics.'
    } else if (status && status >= 500) {
      message = 'The server failed to load metrics. Try again in a moment or check backend logs.'
    } else {
      message = 'Could not reach the server. Check your network connection and try again.'
    }
    return (
      <div className="p-6">
        {Header}
        <p className="text-red-500" role="alert">
          {message}
        </p>
      </div>
    )
  }

  const sourceTypes = metrics?.embeddings_by_source
    ? Object.entries(metrics.embeddings_by_source)
    : []

  return (
    <div className="p-6">
      {Header}

      {/* Top-level metric cards */}
      <div
        role="list"
        aria-label="RAG metrics"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6"
      >
        {/* Total Embeddings */}
        <Card role="listitem">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Embeddings</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div
              className="text-3xl font-bold"
              aria-label={`Total embeddings: ${metrics?.total_embeddings?.toLocaleString() ?? 0}`}
            >
              {metrics?.total_embeddings?.toLocaleString() ?? 0}
            </div>
            <CardDescription>Stored in content_embeddings</CardDescription>
          </CardContent>
        </Card>

        {/* Prompt Cache Hit Rate */}
        <Card role="listitem">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Prompt Cache Hit Rate</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div
              className="text-3xl font-bold"
              aria-label={`Prompt cache hit rate: ${metrics?.cache_hit_rate_pct ?? 0} percent`}
            >
              {metrics?.cache_hit_rate_pct ?? 0}%
            </div>
            <CardDescription>
              {metrics?.cache_hits_7d ?? 0} / {metrics?.total_ai_calls_7d ?? 0} calls (last 7 days)
            </CardDescription>
          </CardContent>
        </Card>

        {/* Avg Retrieval Latency */}
        <Card role="listitem">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Avg Retrieval Latency</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            <div
              className="text-3xl font-bold"
              aria-label={
                metrics?.avg_retrieval_latency_ms != null
                  ? `Average retrieval latency: ${metrics.avg_retrieval_latency_ms} milliseconds`
                  : 'Average retrieval latency: not available'
              }
            >
              {metrics?.avg_retrieval_latency_ms != null
                ? `${metrics.avg_retrieval_latency_ms}ms`
                : 'N/A'}
            </div>
            <CardDescription>7-day average</CardDescription>
          </CardContent>
        </Card>

        {/* Embeddings by Source */}
        <Card role="listitem" aria-label="Embeddings by source">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Embeddings by Source</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          </CardHeader>
          <CardContent>
            {sourceTypes.length > 0 ? (
              <div className="space-y-2">
                {sourceTypes.map(([type, count]) => (
                  <div key={type} className="flex justify-between text-sm">
                    <span className="text-muted-foreground">{type}</span>
                    <span className="font-medium">{count.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No embeddings yet</p>
            )}
          </CardContent>
        </Card>

        {/* Batch API health — renders the three backend fields so operators
            can see stuck batches without opening a DB shell. Tinted red when
            stuck_count > 0 since that's the actionable failure mode. */}
        {(() => {
          const stuck = metrics?.batch_stuck_count ?? 0
          const submitted = metrics?.batch_submitted_count ?? 0
          const oldest = metrics?.batch_oldest_submitted_age_hours
          const isAlerting = stuck > 0
          return (
            <Card
              role="listitem"
              aria-label="Batch API health"
              className={
                isAlerting
                  ? 'border-red-500 bg-red-50 dark:bg-red-950/20'
                  : undefined
              }
            >
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Batch API Health</CardTitle>
                <AlertTriangle
                  className={
                    isAlerting
                      ? 'h-4 w-4 text-red-600'
                      : 'h-4 w-4 text-muted-foreground'
                  }
                  aria-hidden="true"
                />
              </CardHeader>
              <CardContent>
                <div
                  className={
                    isAlerting
                      ? 'text-3xl font-bold text-red-700'
                      : 'text-3xl font-bold'
                  }
                  aria-label={`Stuck batches: ${stuck}`}
                >
                  {stuck.toLocaleString()}
                </div>
                <CardDescription>
                  stuck of {submitted.toLocaleString()} submitted
                  {oldest != null && (
                    <> · oldest {oldest}h</>
                  )}
                </CardDescription>
                {isAlerting && (
                  <p
                    className="mt-2 text-xs text-red-700"
                    role="alert"
                  >
                    {stuck} batch row{stuck === 1 ? '' : 's'} past the stuck threshold —
                    the worker will fail them out on its next cycle.
                  </p>
                )}
              </CardContent>
            </Card>
          )
        })()}
      </div>
    </div>
  )
}
