// Shared constants and types for condition evaluation UI.
// Used by ConditionalLogicConfig (full groups) and EmailConfig (single pre-send check).

export type FieldType = 'text' | 'number' | 'select' | 'select_grouped' | 'date'

export interface FieldDefinition {
  value: string
  label: string
  icon: string
  type: FieldType
  options?: string[]
  grouped_options?: Record<string, Array<{ value: string; label: string }>>
}

export interface Condition {
  id: string
  field: string
  operator: string
  value: string
}

export const FIELD_DEFINITIONS: FieldDefinition[] = [
  { value: 'stage', label: 'Deal Stage', icon: '\u{1F4CA}', type: 'select_grouped', grouped_options: {} },
  { value: 'status', label: 'Deal Status', icon: '\u{1F3AF}', type: 'select', options: ['Open', 'Won', 'Lost'] },
  { value: 'title', label: 'Deal Title', icon: '\u{1F4DD}', type: 'text' },
  { value: 'value', label: 'Deal Value', icon: '\u{1F4B0}', type: 'number' },
  { value: 'probability', label: 'Deal Probability (%)', icon: '\u{1F4C8}', type: 'number' },
  { value: 'owner_name', label: 'Deal Owner', icon: '\u{1F464}', type: 'select', options: [] },
  { value: 'person_name', label: 'Contact Name', icon: '\u{1F465}', type: 'text' },
  { value: 'org_name', label: 'Organization Name', icon: '\u{1F3E2}', type: 'text' },
  { value: 'expected_close_date', label: 'Expected Close Date', icon: '\u{1F4C5}', type: 'date' },
  { value: 'currency', label: 'Currency', icon: '\u{1F4B1}', type: 'select', options: [] },
]

export const OPERATOR_OPTIONS = [
  { value: 'equals', label: 'Equals', symbol: '=' },
  { value: 'not_equals', label: 'Does not equal', symbol: '\u{2260}' },
  { value: 'contains', label: 'Contains', symbol: '\u{220B}' },
  { value: 'not_contains', label: 'Does not contain', symbol: '\u{220C}' },
  { value: 'greater_than', label: 'Greater than', symbol: '>' },
  { value: 'less_than', label: 'Less than', symbol: '<' },
  { value: 'is_empty', label: 'Is empty', symbol: '\u{2205}' },
  { value: 'is_not_empty', label: 'Is not empty', symbol: '\u{25C9}' },
]
