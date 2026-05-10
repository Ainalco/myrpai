import api from './api'

// --- Resource Library Types ---

export interface Resource {
  id: number
  account_id: number
  type: 'link' | 'file'
  label: string
  description: string | null
  url: string | null
  file_size_bytes: number | null
  file_original_name: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export interface EmailResourceConfig {
  resource_id: string
  usage_mode: 'ai_decides' | 'always' | 'custom_prompt' | 'disabled'
  custom_prompt: string | null
}

export interface EmailResourceSettings {
  resources_enabled: boolean
  config: EmailResourceConfig[]
}

export const resourceApi = {
  list: () =>
    api.get<Resource[]>('/resources'),

  create: (data: { type: string; label: string; description?: string; url?: string }) =>
    api.post<Resource>('/resources', data),

  upload: (formData: FormData) =>
    api.post<Resource>('/resources/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  update: (id: number, data: Partial<Resource>) =>
    api.put<Resource>(`/resources/${id}`, data),

  delete: (id: number) =>
    api.delete(`/resources/${id}`),

  toggleActive: (id: number) =>
    api.patch(`/resources/${id}/toggle`),
}
