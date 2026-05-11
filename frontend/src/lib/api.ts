import axios, { AxiosResponse } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:9000'

// API timeout configuration (in milliseconds)
// Default: 90000ms (90 seconds) for long-running AI operations
// Can be overridden via VITE_API_TIMEOUT environment variable
const API_TIMEOUT = import.meta.env.VITE_API_TIMEOUT
  ? parseInt(import.meta.env.VITE_API_TIMEOUT, 10)
  : 90000

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
})

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle auth errors with automatic token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    if (!originalRequest) {
      return Promise.reject(error)
    }

    const requestUrl = originalRequest?.url || ''
    const isRefreshRequest = requestUrl.includes('/auth/refresh')

    if (error.response?.status === 401 && !originalRequest?._retry) {
      // Never try to refresh a failed refresh request, or we can end up
      // recursively calling /auth/refresh forever with a stale token pair.
      if (isRefreshRequest) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')

        const publicPaths = ['/login', '/register']
        const currentPath = window.location.pathname
        if (!publicPaths.includes(currentPath)) {
          sessionStorage.setItem('redirectAfterLogin', currentPath)
          window.location.href = '/login'
        }

        return Promise.reject(error)
      }

      originalRequest._retry = true
      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await api.post('/auth/refresh', { refresh_token: refreshToken })
          localStorage.setItem('access_token', response.data.access_token)
          localStorage.setItem('refresh_token', response.data.refresh_token)
          originalRequest.headers = originalRequest.headers || {}
          originalRequest.headers.Authorization = `Bearer ${response.data.access_token}`
          return api(originalRequest)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          window.location.href = '/login'
        }
      } else {
        // No refresh token - redirect to login
        const publicPaths = ['/login', '/register']
        const currentPath = window.location.pathname

        if (!publicPaths.includes(currentPath)) {
          localStorage.removeItem('access_token')
          sessionStorage.setItem('redirectAfterLogin', currentPath)
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

// Types
export interface OrgInfo {
  id: number
  name: string
  slug: string
  domain: string | null
}

export interface AccountInfo {
  plan_tier: string
  status: string
  acorn_balance: number
  acorn_allocation_mode?: string
  billing_cycle: string | null
  trial_ends_at: string | null
  current_period_ends_at: string | null
}

export interface User {
  id: number
  email: string
  full_name?: string
  is_active: boolean
  role?: string
  is_superadmin?: boolean
  enable_advanced_components?: boolean
  internal_domains?: string
  smtp_host?: string
  smtp_port?: number
  smtp_username?: string
  smtp_use_tls?: boolean
  smtp_from_email?: string
  smtp_from_name?: string
  email_signature?: string
  email_signature_enabled?: boolean
  locked_acorn_allocation?: number | null
  locked_acorn_balance?: number | null
  created_at: string
  org?: OrgInfo
  account?: AccountInfo
}

export interface SMTPSettings {
  smtp_host: string
  smtp_port: number
  smtp_username: string
  smtp_password: string
  smtp_use_tls: boolean
  smtp_from_email: string
  smtp_from_name?: string
}

// Fresh Check rule toggles (issue #178 / #180). Rules 1–7 are user-
// togglable and persist here. Rule 8 (DNC) is locked-on in the UI and
// enforced deterministically by the DB flag, so there is no field for
// it. Missing toggles default to ON — matches FreshCheckSettings
// defaults in backend/workflows.py.
export interface FreshCheckSettings {
  reply_received?: boolean     // rule 1
  inbox_email?: boolean        // rule 2
  activity_logged?: boolean    // rule 3
  pulse_shift?: boolean        // rule 4 — plan-gated to Oak+
  org_signal?: boolean         // rule 5
  crm_change?: boolean         // rule 6
  flagged_note?: boolean       // rule 7
}

export interface RagSettings {
  smart_context_diversity?: boolean
  thin_transcript_prompt?: boolean
  fresh_check?: FreshCheckSettings
}

export interface Workflow {
  id: number
  name: string
  description?: string
  universal_rules?: string
  rag_settings?: RagSettings
  is_active: boolean
  created_at: string
  updated_at?: string
  components: Component[]
  owner_name?: string
}

export interface WorkflowValidationError {
  component_id?: number
  component_name?: string
  field?: string
  message: string
}

export interface WorkflowValidationResponse {
  valid: boolean
  errors: WorkflowValidationError[]
}

export interface Component {
  id: number
  workflow_id: number
  type: string
  name: string
  description?: string
  configuration: Record<string, any>
  position_x: number
  position_y: number
  order: number
  created_at: string
  updated_at?: string
}

export interface TraceEntry {
  id: string
  type: string
  started_at: string
  duration_ms: number
  request: Record<string, any> | null
  response: Record<string, any> | null
  error: string | null
  metadata: Record<string, any>
}

export interface Connection {
  id: number
  from_component_id: number
  to_component_id: number
  condition?: string
  created_at: string
}

// Persisted RAG-only trace stored on Execution.rag_trace; same shape as
// TraceEntry but with looser optionality since fields may be omitted by the
// trim step in _filter_rag_trace_for_persistence.
export type RagTraceEntry = TraceEntry

export interface Execution {
  id: number
  workflow_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at: string
  completed_at?: string
  total_execution_time?: number
  results?: Record<string, any>
  error_message?: string
  acorns_used?: number
  rag_trace?: RagTraceEntry[] | null
  component_executions: ComponentExecution[]
}

export interface ComponentExecution {
  id: number
  component_id: number
  component_name: string
  component_type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at?: string
  completed_at?: string
  execution_time?: number
  input_data?: Record<string, any>
  output_data?: Record<string, any>
  error_message?: string
}

export interface WorkflowStats {
  total_workflows: number
  active_workflows: number
  total_executions: number
  successful_executions: number
  failed_executions: number
  avg_execution_time?: number
}

// Admin types
export interface AdminUserStats {
  id: number
  email: string
  full_name?: string
  is_active: boolean
  is_superadmin: boolean
  created_at?: string
  org_id?: number
  org_name?: string
  workflow_count: number
  execution_count: number
  total_tokens: number
  total_prompt_tokens: number
  total_completion_tokens: number
  cost: number           // Billable to user (baseline, cache-agnostic)
  actual_cost?: number   // Actual Anthropic cost (with prompt cache tier pricing)
  acorns_spent?: number
  acorn_balance?: number
  plan?: string
  last_active?: string
}

export interface AdminOrgMemberStats extends AdminUserStats {
  role: string
}

export interface AdminOrgStats {
  org: {
    id: number
    name: string
    slug: string
    domain?: string
    created_at?: string
  }
  plan: string
  allocation_mode: string
  acorn_balance: number
  total_cost: number              // Billable to users
  total_actual_cost?: number      // Actual Anthropic cost
  total_acorns_spent: number
  total_tokens: number
  members: AdminOrgMemberStats[]
}

export interface AdminOverview {
  total_users: number
  total_workflows: number
  total_executions: number
  total_tokens: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cost: number              // Billable to users
  total_actual_cost?: number      // Actual Anthropic cost
  users: AdminUserStats[]
}

export interface DailyUserStats {
  tokens: number
  prompt_tokens: number
  completion_tokens: number
  executions: number
  cost: number           // Billable to user
  actual_cost?: number   // Actual Anthropic cost
}

export interface DailyStat {
  date: string
  tokens: number
  prompt_tokens: number
  completion_tokens: number
  executions: number
  cost: number           // Billable to users
  actual_cost?: number   // Actual Anthropic cost
  by_user: Record<string, DailyUserStats>
}

export interface UsageOverTime {
  days: number
  daily_stats: DailyStat[]
}

export interface AiModel {
  id: number
  model_id: string
  display_name: string
  input_cost_per_million: number
  output_cost_per_million: number
  is_active: boolean
  created_at: string | null
}

export interface RagMetrics {
  total_embeddings: number
  embeddings_by_source: Record<string, number>
  cache_hit_rate_pct: number
  total_ai_calls_7d: number
  cache_hits_7d: number
  avg_retrieval_latency_ms: number | null
  // Anthropic Batch API health — mirrors the three fields the admin endpoint
  // computes for operator visibility. batch_stuck_count uses the same
  // threshold (rag.batch_stuck_threshold_hours) the batch worker acts on.
  batch_submitted_count: number
  batch_stuck_count: number
  batch_oldest_submitted_age_hours: number | null
}

export interface AdminUserDetail {
  user: {
    id: number
    email: string
    full_name?: string
    is_active: boolean
    created_at?: string
  }
  total_tokens: number
  total_prompt_tokens: number
  total_completion_tokens: number
  total_cost: number              // Billable to user
  total_actual_cost?: number      // Actual Anthropic cost
  workflows: Array<{
    id: number
    name: string
    is_active: boolean
    created_at?: string
    execution_count: number
    total_tokens: number
    cost: number
    actual_cost?: number
    last_executed?: string
  }>
  usage_by_source: Array<{
    source: string
    call_count: number
    tokens: number
  }>
  recent_activity: Array<{
    type: 'pipeline' | 'component_test'
    label: string
    workflow_name: string
    status: string
    started_at: string | null
    total_tokens: number
    total_prompt_tokens: number
    total_completion_tokens: number
    cost: number
    actual_cost?: number
    model: string
  }>
}

export interface ComponentType {
  name: string
  description: string
  icon: string
  category: string
  is_advanced?: boolean
}

export interface ApiKeyInfo {
  id: number
  service_name: string
  is_active: boolean
  created_at: string
  updated_at?: string
  last_used_at?: string
}

export interface ApiKeyStatus {
  service_name: string
  configured: boolean
}

export interface ApiKeyTestResponse {
  success: boolean
  message: string
  service_name: string
}

// Auth API
export const authApi = {
  login: (data: { email: string; password: string }) =>
    api.post<{ access_token: string; refresh_token: string; token_type: string }>('/auth/login', data),

  register: (data: {
    email: string
    password: string
    full_name?: string
    company_name?: string
    team_size?: string
    current_crm?: string
    meeting_tool?: string
    meetings_per_week?: string
    deal_cycle?: string
    challenge?: string
  }) => api.post<User>('/auth/register', data),

  getMe: () => api.get<User>('/auth/me'),

  updateProfile: (data: { full_name: string }) =>
    api.put<User>('/auth/profile', data),

  updateSettings: (internalDomains: string) =>
    api.patch<{ success: boolean; message: string; internal_domains: string }>(
      '/auth/me/settings',
      null,
      {
        params: { internal_domains: internalDomains }
      }
    ),

  updateSMTPSettings: (settings: SMTPSettings) =>
    api.post<{ success: boolean; message: string }>(
      '/auth/me/smtp',
      settings
    ),

  testSMTPConnection: (settings: SMTPSettings) =>
    api.post<{ success: boolean; message: string }>(
      '/auth/me/smtp/test',
      settings
    ),

  updateEmailSignature: (data: { email_signature?: string; email_signature_enabled?: boolean }) =>
    api.put<{ success: boolean; message: string }>(
      '/auth/me/email-signature',
      data
    ),
}

// Workflow API
export const workflowApi = {
  getAll: () => api.get<Workflow[]>('/workflows/'),

  getById: (id: number) => api.get<Workflow>(`/workflows/${id}`),

  create: (data: { name: string; description?: string; universal_rules?: string }) =>
    api.post<Workflow>('/workflows/', data),

  update: (
    id: number,
    data: {
      name?: string
      description?: string
      universal_rules?: string
      is_active?: boolean
      rag_settings?: Partial<RagSettings>
    }
  ) => api.put<Workflow>(`/workflows/${id}`, data),

  delete: (id: number) => api.delete(`/workflows/${id}`),

  getStats: () => api.get<WorkflowStats>('/workflows/stats/dashboard'),

  export: (id: number) => api.get(`/workflows/${id}/export`),

  import: (id: number, data: any) => api.post(`/workflows/${id}/import`, data),

  validate: (id: number) =>
    api.post<WorkflowValidationResponse>(`/workflows/${id}/validate`),
}

// Component API
export const componentApi = {
  getTypes: () => api.get<Record<string, ComponentType>>('/components/types'),

  getByWorkflow: (workflowId: number) =>
    api.get<Component[]>(`/components/${workflowId}/components`),

  create: (
    workflowId: number,
    data: {
      type: string
      name: string
      description?: string
      configuration?: Record<string, any>
      position_x?: number
      position_y?: number
      order?: number
    }
  ) => api.post<Component>(`/components/${workflowId}/components`, data),

  update: (
    workflowId: number,
    componentId: number,
    data: {
      name?: string
      description?: string
      configuration?: Record<string, any>
      position_x?: number
      position_y?: number
      order?: number
    }
  ) =>
    api.put<Component>(
      `/components/${workflowId}/components/${componentId}`,
      data
    ),

  delete: (workflowId: number, componentId: number) =>
    api.delete(`/components/${workflowId}/components/${componentId}`),

  updateConfig: (componentId: number, configuration: Record<string, any>) =>
    api.put<Component>(`/components/${componentId}/config`, { configuration }),

  test: (
    componentId: number,
    testData?: { test_data?: any; fireflies_transcript_id?: string },
    options?: { trace?: boolean }
  ) =>
    api.post<{ success: boolean; results: any; trace?: TraceEntry[] }>(
      `/components/${componentId}/test${options?.trace ? '?trace=true' : ''}`,
      testData || {}
    ),

  testPreSendCheck: (payload: {
    test_type: "crm" | "ai_filter";
    component_id: number;
    condition_groups?: any[];
    group_logic?: string;
    data_source?: string;
    ai_prompt?: string;
    condition_operator?: string;
    condition_value?: string;
    case_sensitive?: boolean;
  }) =>
    api.post<{ success: boolean; passed: boolean; reason: string; duration: number }>(
      `/components/pre-send-check/test`, payload
    ),

  getAvailableVariables: (componentId: number) =>
    api.get<{ component_id: number; available_variables: Array<{ value: string; label: string }> }>(
      `/components/${componentId}/available-variables`
    ),

  getPipedriveFields: (actionType: string) =>
    api.get<{ success: boolean; action_type: string; fields: Array<{ value: string; label: string; type: string; is_custom: boolean; required: boolean }> }>(
      `/components/pipedrive/fields/${actionType}`
    ),

  clearPipedriveCache: () =>
    api.post<{ success: boolean; message: string; cache_cleared: boolean }>(
      `/components/pipedrive/cache/clear`
    ),

  getPipedrivePipelines: () =>
    api.get<{
      success: boolean;
      pipelines: Array<{ id: number; name: string }>
    }>(
      `/components/pipedrive/pipelines`
    ),

  getPipedriveStages: () =>
    api.get<{
      success: boolean;
      stages: string[];
      stage_mapping: Record<string, string>;
      stages_by_pipeline: Record<string, {
        pipeline_name: string;
        stages: Array<{ id: string; name: string }>;
      }>;
    }>(
      `/components/pipedrive/stages`
    ),

  getPipedriveUsers: () =>
    api.get<{ success: boolean; users: string[] }>(
      `/components/pipedrive/users`
    ),

  getPipedriveCurrencies: () =>
    api.get<{ success: boolean; currencies: string[] }>(
      `/components/pipedrive/currencies`
    ),

  getConnections: (workflowId: number) =>
    api.get<Connection[]>(`/components/${workflowId}/connections`),

  createConnection: (
    workflowId: number,
    data: {
      from_component_id: number
      to_component_id: number
      condition?: string
    }
  ) => api.post<Connection>(`/components/${workflowId}/connections`, data),

  deleteConnection: (workflowId: number, connectionId: number) =>
    api.delete(`/components/${workflowId}/connections/${connectionId}`),
}

// Execution API
export const executionApi = {
  getByWorkflow: (workflowId: number) =>
    api.get<Execution[]>(`/executions/${workflowId}/executions`),

  execute: (workflowId: number, testMode = false, firefliesTranscriptId?: string) =>
    api.post<Execution>(`/executions/${workflowId}/execute`, {
      workflow_id: workflowId,
      test_mode: testMode,
      fireflies_transcript_id: firefliesTranscriptId,
    }),

  getById: (workflowId: number, executionId: number) =>
    api.get<Execution>(`/executions/${workflowId}/executions/${executionId}`),

  getLatest: (workflowId: number) =>
    api.get<Execution>(`/executions/${workflowId}/latest`),

  getStats: (workflowId: number) =>
    api.get(`/executions/${workflowId}/executions/stats`),
}

// API Keys API
export const apiKeyApi = {
  getAll: () => api.get<ApiKeyInfo[]>('/api-keys'),

  getStatus: (serviceName: string) =>
    api.get<ApiKeyStatus>(`/api-keys/${serviceName}`),

  createOrUpdate: (serviceName: string, apiKey: string) =>
    api.post<ApiKeyInfo>('/api-keys', {
      service_name: serviceName,
      api_key: apiKey,
    }),

  delete: (serviceName: string) => api.delete(`/api-keys/${serviceName}`),

  test: (serviceName: string, apiKey: string) =>
    api.post<ApiKeyTestResponse>('/api-keys/test', {
      service_name: serviceName,
      api_key: apiKey,
    }),
}

//twilioApi
export interface TwilioSettingsPayload {
  account_sid: string
  auth_token: string
  from_number: string
}

export const twilioApi = {
  saveSettings: (data: TwilioSettingsPayload) =>
    api.post<{ success: boolean; message: string }>('/api-keys/twilio', data),
}

// Fireflies Transcript API
export interface FirefliesTranscriptSummary {
  id: string
  title: string
  date?: string
  duration: number
  participants: string[]
  participant_count: number
}

export interface FirefliesTranscriptData {
  transcript: string
  sentences: Array<{ speaker_name: string; text: string }>
  participants: Array<{ name: string; email: string }>
  meeting_title: string
  meeting_date?: string
  duration: number
  source: string
  meeting_id: string
}

export const firefliesApi = {
  listTranscripts: (limit?: number) =>
    api.get<FirefliesTranscriptSummary[]>('/fireflies/transcripts', {
      params: { limit: limit || 50 }
    }),

  getTranscript: (transcriptId: string) =>
    api.get<FirefliesTranscriptData>(`/fireflies/transcripts/${transcriptId}`),
}

// Contact Types (for email queue enhancements)
export interface ContactInfo {
  id: number
  email: string
  name?: string
  title?: string
  company?: string
  avatar_initials?: string
}

export interface ContactActivity {
  id: number
  activity_type: 'email_sent' | 'email_opened' | 'reply_received' | 'meeting' | 'bounced'
  title?: string
  occurred_at: string
  is_new: boolean
}

export interface Contact extends ContactInfo {
  last_contacted_at?: string
  contact_count: number
  created_at: string
  updated_at?: string
  activities?: ContactActivity[]
}

// --- Contact System V2 Types ---

export interface ContactStats {
  sent: number
  received: number
  rate: string
  meetings: number
  sequences: number
  openDeals: number
  dealValue: number
}

export interface ContactPulse {
  summary: string | null
  sentiment: string | null
  engagement: string | null
  intent: string | null
  action: string | null
  topics: string[]
  objections: string[]
  lastMeeting: string | null
}

export interface ContactDeal {
  id: number
  title: string
  status: string
  stage: string | null
  value: number | null
  expected: string | null
  externalUrl: string | null
}

export interface TimelineEvent {
  id: number
  type: string
  dir: string | null
  source: string | null
  subject?: string
  summary: string | null
  at: string | null
  deal?: string
}

export interface ThreadMessage {
  id: string
  from: string  // "you" or sender email
  to: string
  subject?: string
  body?: string
  at?: string
}

export interface Thread {
  id: string
  summary: string | null
  sentiment: string | null
  status: string | null
  msgs: number
  lastAt: string | null
  messages: ThreadMessage[]
}

export interface Meeting {
  id: number
  date: string | null
  source: string | null
  summary: string | null
  keyPoints: string[]
  objections: string[]
  signals: string[]
  stage: string | null
}

export interface ContactListItem {
  id: number
  name: string | null
  email: string
  orgId: number | null
  orgName: string | null
  status: string
  pipedrive: boolean
  lastActivity: string | null
  stats: ContactStats
  emails: string[]
}

export interface ContactListResponse {
  items: ContactListItem[]
  counts: { active: number; paused: number; dnc: number; bounced: number }
  nextCursor: number | null
  hasMore: boolean
}

export interface ContactDetail extends ContactListItem {
  pulse: ContactPulse  // Always present — API returns default pulse if none generated
  deals: ContactDeal[]
  timeline: TimelineEvent[]
  threads: Thread[]
  meetings: Meeting[]
}

export interface OrgListItem {
  id: number
  name: string
  domain: string | null
  contacts: number
  openDeals: number
  totalValue: number
  dnc: boolean
  dncProp: boolean
}

export interface OrgDetail extends OrgListItem {
  persons: { id: number; name: string | null; email: string; status: string }[]
}

// Email Queue Types
export interface EmailQueueItem {
  id: number
  user_id: number
  workflow_id?: number
  execution_id?: number
  component_id?: number
  recipient_email: string
  recipient_name?: string
  subject: string
  body: string
  cc?: string[]
  bcc?: string[]
  channel?: 'email' | 'sms'
  recipient_phone?: string | null
  character_count?: number | null
  sms_segments?: number | null
  twilio_message_sid?: string | null
  delivery_status?: string | null
  scheduled_at: string
  sent_at?: string
  status: 'pending' | 'sent' | 'failed' | 'cancelled'
  error_message?: string
  retry_count: number
  max_retries: number
  created_at: string
  updated_at?: string
  // Enhanced fields
  contact_id?: number
  original_subject?: string
  original_body?: string
  edit_source?: 'ai' | 'manual' | null
  approval_status: 'pending' | 'approved' | 'skipped'
  approved_at?: string
  sequence_config_id?: number
  sequence_position?: number
  sequence_total?: number
  // AI reasoning
  timing_reason?: string
  generation_reason?: string
  org_warning?: string | null
  thread_id?: string | null
  message_id_header?: string | null
  thread_parent_component_id?: number | null
  thread_parent_component_name?: string | null
  thread_parent_queue_id?: number | null
  thread_fallback_reason?: string | null
  sender_provider?: 'gmail' | 'outlook' | 'smtp' | string | null
  sender_account_email?: string | null
  // Fresh Check audit (#178) — populated by the pre-send gate. Null when
  // the email predates Fresh Check or fell through on a cold path.
  fresh_check_action?:
  | 'continue'
  | 'cancel_sequence'
  | 'cancel_email'
  | 'skip_email'
  | 'reschedule'
  | null
  fresh_check_rule_triggered?:
  | 'reply_received'
  | 'inbox_email'
  | 'activity_logged'
  | 'pulse_shift'
  | 'org_signal'
  | 'crm_change'
  | 'flagged_note'
  | 'dnc'
  | 'none'
  | null
  fresh_check_reason?: string | null
  fresh_check_resume_date?: string | null   // ISO date (YYYY-MM-DD)
  // Nested data
  contact?: ContactInfo
  activities?: ContactActivity[]
  sequence_name?: string
}

export interface EmailQueueStats {
  total: number
  pending: number
  approved: number
  sent: number
  sent_today: number
  failed: number
  cancelled: number
  skipped: number
}

export interface AIEditResponse {
  id: number
  modified_subject: string
  modified_body: string
  changes_summary: string
}

// Email Queue API
export const emailQueueApi = {
  getAll: (status?: string, approvalStatus?: string, limit = 100, offset = 0) =>
    api.get<EmailQueueItem[]>('/emails/', {
      params: { status, approval_status: approvalStatus, limit, offset }
    }),

  getStats: () =>
    api.get<EmailQueueStats>('/emails/stats'),

  getById: (emailId: number) =>
    api.get<EmailQueueItem>(`/emails/${emailId}`),

  cancel: (emailId: number) =>
    api.delete<{ success: boolean; message: string }>(`/emails/${emailId}`),

  retry: (emailId: number) =>
    api.post<{ success: boolean; message: string }>(`/emails/${emailId}/retry`),

  processQueue: () =>
    api.post<{ success: boolean; message: string; stats: any }>('/emails/process-queue'),

  // Enhanced email queue methods
  update: (emailId: number, data: { subject?: string; body?: string; edit_source?: string }) =>
    api.put<EmailQueueItem>(`/emails/${emailId}`, data),

  aiEdit: (emailId: number, prompt: string) =>
    api.post<AIEditResponse>(`/emails/${emailId}/ai-edit`, { prompt }),

  revert: (emailId: number) =>
    api.post<EmailQueueItem>(`/emails/${emailId}/revert`),

  approve: (emailId: number) =>
    api.post<{ success: boolean; message: string }>(`/emails/${emailId}/approve`),

  skip: (emailId: number) =>
    api.post<{ success: boolean; message: string }>(`/emails/${emailId}/skip`),

  unskip: (emailId: number) =>
    api.post<{ success: boolean; message: string }>(`/emails/${emailId}/unskip`),

  unapprove: (emailId: number) =>
    api.post<{ success: boolean; message: string }>(`/emails/${emailId}/unapprove`),

  approveAll: () =>
    api.post<{ success: boolean; approved_count: number; message: string }>('/emails/approve-all'),

  // Fresh Check override (#178 T5): clear the fresh_check_* audit fields
  // and requeue the email for immediate send. Refused for DNC stops —
  // admins must clear the underlying DB flag first.
  overrideFreshCheck: (emailId: number) =>
    api.post<{ success: boolean; message: string }>(
      `/emails/${emailId}/override-fresh-check`,
    ),
}

export interface SMSQueueItem extends EmailQueueItem {
  channel: 'sms'
  recipient_phone?: string | null
  character_count?: number | null
  sms_segments?: number | null
  twilio_message_sid?: string | null
  delivery_status?: string | null
}

export const smsQueueApi = {
  getAll: (status?: string, approvalStatus?: string, limit = 100, offset = 0) =>
    api.get<SMSQueueItem[]>('/sms/queue', {
      params: { status, approval_status: approvalStatus, limit, offset },
    }),

  approve: (id: number) =>
    api.post<{ success: boolean; message: string }>(`/sms/queue/${id}/approve`),

  edit: (id: number, body: string) =>
    api.post<SMSQueueItem>(`/sms/queue/${id}/edit`, { body }),

  skip: (id: number) =>
    api.post<{ success: boolean; message: string }>(`/sms/queue/${id}/skip`),

  delete: (id: number) =>
    api.delete<{ success: boolean; message: string }>(`/sms/queue/${id}`),
}

// Contacts API (legacy — used by email queue)
export const contactsApiLegacy = {
  getAll: (search?: string, limit = 100, offset = 0) =>
    api.get<Contact[]>('/contacts/', {
      params: { search, limit, offset }
    }),

  getById: (contactId: number) =>
    api.get<Contact>(`/contacts/${contactId}`),

  getByEmail: (email: string) =>
    api.get<Contact | null>(`/contacts/by-email/${encodeURIComponent(email)}`),

  getActivities: (contactId: number, limit = 20) =>
    api.get<ContactActivity[]>(`/contacts/${contactId}/activities`, {
      params: { limit }
    }),

  markRead: (contactId: number) =>
    api.post<{ success: boolean; marked_read: number }>(`/contacts/${contactId}/mark-read`),
}

// Contacts API V2
export const contactsApi = {
  list: (params?: { search?: string; status?: string; cursor?: number; limit?: number }) =>
    api.get<ContactListResponse>('/contacts/', { params }),

  getById: (contactId: number) =>
    api.get<ContactDetail>(`/contacts/${contactId}`),

  create: (data: { email: string; name?: string; organization_name?: string }) =>
    api.post<ContactDetail>('/contacts/', data),

  update: (contactId: number, data: { name?: string; email?: string; title?: string; company?: string }) =>
    api.put<ContactDetail>(`/contacts/${contactId}`, data),

  updateStatus: (contactId: number, status: string) =>
    api.put(`/contacts/${contactId}/status`, { status }),

  delete: (contactId: number) =>
    api.delete(`/contacts/${contactId}`),

  addNote: (contactId: number, content: string) =>
    api.post(`/contacts/${contactId}/note`, { content }),

  merge: (keepId: number, mergeId: number) =>
    api.post(`/contacts/${keepId}/merge`, { merge_id: mergeId }),

  refreshPulse: (contactId: number) =>
    api.post(`/contacts/${contactId}/refresh-pulse`),

  syncMeetings: (limit = 50) =>
    api.post<{ success: boolean; transcriptsChecked: number; transcriptsSynced: number; meetingsCreated: number; contactsLinked: number }>(`/contacts/sync-meetings`, null, { params: { limit } }),
}

export const contactOrgsApi = {
  list: (params?: { search?: string; cursor?: number; limit?: number }) =>
    api.get<{ items: OrgListItem[] }>('/contact-organizations/', { params }),

  getById: (orgId: number) =>
    api.get<OrgDetail>(`/contact-organizations/${orgId}`),

  update: (orgId: number, data: { name?: string; do_not_contact_propagation?: boolean }) =>
    api.put<OrgDetail>(`/contact-organizations/${orgId}`, data),
}

// Email Sequence Types
export interface SkipCondition {
  type: string // "deal_stage", "deal_status", "contact_field", "days_since_last_email", "reply_received"
  operator: string // "equals", "not_equals", "contains", "greater_than", "less_than"
  value: any
  field?: string // For custom field conditions
}

export interface SequenceEmail {
  id: number
  sequence_config_id: number
  order: number
  name: string
  subject: string
  body: string
  timing_mode: string // "relative" or "specific"
  delay_value?: number
  delay_unit?: string // "minutes", "hours", "days", "weeks"
  specific_day?: string
  specific_time?: string
  ai_decides_timing: boolean
  ai_timing_context?: string
  is_enabled: boolean
  generation_prompt?: string
  use_variables: string[]
  created_at: string
  updated_at?: string
}

export interface EmailSequenceConfig {
  id: number
  workflow_id: number
  name: string
  is_enabled: boolean
  ai_optimize_timing: boolean
  ai_optimization_prompt?: string
  send_method?: string
  timezone?: string
  business_hours_only: boolean
  business_hours_start?: string
  business_hours_end?: string
  business_days?: string[]
  skip_conditions?: SkipCondition[]
  emails?: SequenceEmail[]
  created_at: string
  updated_at?: string
}

export interface SequenceEmailCreate {
  order?: number
  name?: string
  subject: string
  body: string
  timing_mode?: string
  delay_value?: number
  delay_unit?: string
  specific_day?: string
  specific_time?: string
  ai_decides_timing?: boolean
  ai_timing_context?: string
  is_enabled?: boolean
  generation_prompt?: string
  use_variables?: string[]
}

export interface EmailSequenceConfigCreate {
  name?: string
  is_enabled?: boolean
  ai_optimize_timing?: boolean
  ai_optimization_prompt?: string
  send_method?: string
  timezone?: string
  business_hours_only?: boolean
  business_hours_start?: string
  business_hours_end?: string
  business_days?: string[]
  skip_conditions?: SkipCondition[]
}

// Email Sequence API
export const emailSequenceApi = {
  // Sequence config CRUD
  getConfig: (workflowId: number) =>
    api.get<EmailSequenceConfig | null>(`/email-sequences/workflow/${workflowId}`),

  createConfig: (workflowId: number, data: EmailSequenceConfigCreate) =>
    api.post<EmailSequenceConfig>(`/email-sequences/workflow/${workflowId}`, data),

  updateConfig: (workflowId: number, data: Partial<EmailSequenceConfigCreate>) =>
    api.put<EmailSequenceConfig>(`/email-sequences/workflow/${workflowId}`, data),

  deleteConfig: (workflowId: number) =>
    api.delete<{ message: string }>(`/email-sequences/workflow/${workflowId}`),

  // Sequence emails CRUD
  addEmail: (configId: number, data: SequenceEmailCreate) =>
    api.post<SequenceEmail>(`/email-sequences/${configId}/emails`, data),

  updateEmail: (emailId: number, data: Partial<SequenceEmailCreate>) =>
    api.put<SequenceEmail>(`/email-sequences/emails/${emailId}`, data),

  deleteEmail: (emailId: number) =>
    api.delete<{ message: string }>(`/email-sequences/emails/${emailId}`),

  reorderEmails: (configId: number, emailIds: number[]) =>
    api.post<{ message: string }>(`/email-sequences/${configId}/emails/reorder`, emailIds),

  // AI features
  generateEmails: (workflowId: number, data: {
    transcript_summary: string
    num_emails?: number
    custom_prompt?: string
    tone?: string
    include_variables?: string[]
  }) =>
    api.post<{ emails: SequenceEmail[]; total_generated: number }>(
      `/email-sequences/workflow/${workflowId}/generate-emails`,
      data
    ),

  optimizeTiming: (workflowId: number, data: {
    transcript_summary: string
    emails: Array<{ id: number; subject: string; body: string }>
    custom_prompt?: string
  }) =>
    api.post<{ optimizations: Array<{ email_id: number; suggested_timing: any; reasoning: string }> }>(
      `/email-sequences/workflow/${workflowId}/optimize-timing`,
      data
    ),

  previewExecution: (workflowId: number, sampleData: Record<string, any>) =>
    api.post<{
      emails: Array<{
        order: number
        subject: string
        body: string
        scheduled_for: string
        skip_status: string
      }>
    }>(`/email-sequences/workflow/${workflowId}/preview`, sampleData),
}

// Gmail API Types (proxied through our backend to avoid CORS)
export interface GmailAccount {
  id: number
  email: string
  display_name?: string
  is_active: boolean
  token_status?: string
  created_at?: string
}

export interface GmailAuthUrlResponse {
  success: boolean
  auth_url?: string
  error?: string
}

export interface GmailAccountsResponse {
  success: boolean
  accounts: GmailAccount[]
  error?: string
}

export interface GmailDisconnectResponse {
  success: boolean
  message?: string
  error?: string
}

export interface GmailSendEmailRequest {
  account_id: number
  to: string
  to_name?: string
  subject: string
  body: string
  cc?: string[]
  bcc?: string[]
  track_opens?: boolean
  track_clicks?: boolean
}

export interface GmailSendEmailResponse {
  success: boolean
  message_id?: string
  email_id?: number
  error?: string
}

// Gmail API Functions (via backend proxy)
export const gmailApiService = {
  // Get OAuth URL to connect Gmail
  getAuthUrl: () =>
    api.get<GmailAuthUrlResponse>('/gmail/auth-url'),

  // Disconnect a Gmail account
  disconnect: (accountId: number) =>
    api.post<GmailDisconnectResponse>(`/gmail/disconnect/${accountId}`),

  // List all connected Gmail accounts
  getAccounts: () =>
    api.get<GmailAccountsResponse>('/gmail/accounts'),

  // Send an email via Gmail
  sendEmail: (data: GmailSendEmailRequest) =>
    api.post<GmailSendEmailResponse>('/gmail/send', data),
}

// Outlook API Types (proxied through our backend to avoid CORS)
export interface OutlookAccount {
  id: number
  email: string
  display_name?: string
  is_active: boolean
  token_status?: string
  created_at?: string
}

export interface OutlookAuthUrlResponse {
  success: boolean
  auth_url?: string
  error?: string
}

export interface OutlookAccountsResponse {
  success: boolean
  accounts: OutlookAccount[]
  error?: string
}

export interface OutlookDisconnectResponse {
  success: boolean
  message?: string
  error?: string
}

export interface OutlookSendEmailRequest {
  account_id: number
  to: string
  to_name?: string
  subject: string
  body: string
  cc?: string[]
  bcc?: string[]
  track_opens?: boolean
  track_clicks?: boolean
}

export interface OutlookSendEmailResponse {
  success: boolean
  message_id?: string
  email_id?: number
  error?: string
}

// Outlook API Functions (via backend proxy)
export const outlookApiService = {
  // Get OAuth URL to connect Outlook
  getAuthUrl: () =>
    api.get<OutlookAuthUrlResponse>('/outlook/auth-url'),

  // Disconnect an Outlook account
  disconnect: (accountId: number) =>
    api.post<OutlookDisconnectResponse>(`/outlook/disconnect/${accountId}`),

  // List all connected Outlook accounts
  getAccounts: () =>
    api.get<OutlookAccountsResponse>('/outlook/accounts'),

  // Send an email via Outlook
  sendEmail: (data: OutlookSendEmailRequest) =>
    api.post<OutlookSendEmailResponse>('/outlook/send', data),
}

// Admin API
export const adminApi = {
  getOverview: () =>
    api.get<AdminOverview>('/admin/stats/overview'),

  getUsageOverTime: (days = 30) =>
    api.get<UsageOverTime>('/admin/stats/usage-over-time', {
      params: { days },
    }),

  getUserDetail: (userId: number, params?: { days?: number; start_date?: string; end_date?: string }) =>
    api.get<AdminUserDetail>(`/admin/stats/user/${userId}`, { params: params || {} }),

  resetUserUsage: (userId: number) =>
    api.delete(`/admin/stats/user/${userId}/reset-usage`),

  getOrgStats: (orgId: number) =>
    api.get<AdminOrgStats>(`/admin/stats/org/${orgId}`),

  getModels: () =>
    api.get<AiModel[]>('/admin/models'),

  createModel: (data: { model_id: string; display_name: string; input_cost_per_million: number; output_cost_per_million: number }) =>
    api.post<AiModel>('/admin/models', data),

  updateModel: (id: number, data: Partial<{ display_name: string; input_cost_per_million: number; output_cost_per_million: number }>) =>
    api.put<AiModel>(`/admin/models/${id}`, data),

  activateModel: (id: number) =>
    api.put<{ message: string; model_id: string }>(`/admin/models/${id}/activate`),

  deleteModel: (id: number) =>
    api.delete(`/admin/models/${id}`),

  getRagMetrics: () =>
    api.get<RagMetrics>('/admin/rag/metrics'),
}

// Billing API
export const billingApi = {
  getStatus: () => api.get('/billing/status'),
  getPrices: () => api.get('/billing/prices'),
  getTransactions: (limit = 20, offset = 0) =>
    api.get(`/billing/transactions?limit=${limit}&offset=${offset}`),
  getAcornBalance: () => api.get<{ acorn_balance: number; acorn_allocation_mode?: string; locked_acorn_allocation?: number | null; locked_acorn_balance?: number | null }>('/billing/acorns'),
  upgrade: (plan: string, cycle: string) =>
    api.post<{ action: string; price_id?: string; plan?: string; cycle?: string; message: string }>(
      '/billing/upgrade',
      { plan, cycle }
    ),
  cancel: () =>
    api.post<{ ok: boolean; message: string }>('/billing/cancel'),
}

// Demo Transcripts API
export const demoTranscriptsApi = {
  list: () => api.get('/demo-transcripts'),
  get: (id: string) => api.get(`/demo-transcripts/${id}`),
}

// Team API
export const teamApi = {
  listMembers: () => api.get('/team/members'),
  invite: (data: { email: string; role: string }) => api.post('/team/invite', data),
  listInvitations: () => api.get('/team/invitations'),
  revokeInvitation: (id: number) => api.delete(`/team/invitations/${id}`),
  getInviteInfo: (token: string) => api.get(`/team/invite/${token}`),
  acceptInvite: (token: string, data: { token: string; password: string; full_name?: string }) =>
    api.post(`/team/invite/${token}/accept`, data),
  changeRole: (userId: number, role: string) => api.put(`/team/members/${userId}/role`, { role }),
  removeMember: (userId: number) => api.delete(`/team/members/${userId}`),
  transferOwnership: (userId: number) => api.post('/team/transfer-ownership', { new_owner_user_id: userId }),
  getAllocationMode: () => api.get('/team/acorn-allocation'),
  setAllocationMode: (mode: string) => api.put('/team/acorn-allocation/mode', { mode }),
  allocateAcorns: (userId: number, amount: number) => api.put('/team/acorn-allocation/user', { user_id: userId, amount }),
  getAuditLog: (params?: { action?: string; user_id?: number; limit?: number; offset?: number }) =>
    api.get('/team/audit-log', { params }),
  deleteOrganization: () => api.delete('/team/organization'),
}

export default api
