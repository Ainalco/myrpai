import React from 'react'
import type { Condition, FieldDefinition } from './conditionConstants'

/**
 * Renders the correct value input (text, number, select, grouped select, date)
 * based on the field type of the selected condition field.
 *
 * Used by both ConditionalLogicConfig (per-condition in groups) and
 * EmailConfig (single pre-send check condition).
 */
export function renderValueInput(
  condition: Condition,
  groupId: string,
  fieldDefinitions: FieldDefinition[],
  updateCondition: (groupId: string, conditionId: string, field: keyof Condition, value: string) => void
) {
  const fieldDef = fieldDefinitions.find(f => f.value === condition.field)

  if (!fieldDef) {
    return (
      <input
        type="text"
        className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
        placeholder="Enter value..."
        value={condition.value}
        onChange={(e) => updateCondition(groupId, condition.id, 'value', e.target.value)}
      />
    )
  }

  // Grouped select (for stages)
  if (fieldDef.type === 'select_grouped' && fieldDef.grouped_options) {
    return (
      <div className="relative">
        <select
          className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
          value={condition.value}
          onChange={(e) => updateCondition(groupId, condition.id, 'value', e.target.value)}
        >
          <option value="">Select {fieldDef.label.toLowerCase()}...</option>
          {Object.entries(fieldDef.grouped_options).map(([groupName, options]) => (
            <optgroup key={groupName} label={groupName}>
              {options.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">&#9660;</span>
      </div>
    )
  }

  // Regular select
  if (fieldDef.type === 'select' && fieldDef.options && fieldDef.options.length > 0) {
    return (
      <div className="relative">
        <select
          className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
          value={condition.value}
          onChange={(e) => updateCondition(groupId, condition.id, 'value', e.target.value)}
        >
          <option value="">Select {fieldDef.label.toLowerCase()}...</option>
          {fieldDef.options.map(option => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">&#9660;</span>
      </div>
    )
  }

  // Number input
  if (fieldDef.type === 'number') {
    return (
      <input
        type="number"
        className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
        placeholder="Enter number..."
        value={condition.value}
        onChange={(e) => updateCondition(groupId, condition.id, 'value', e.target.value)}
      />
    )
  }

  // Date input
  if (fieldDef.type === 'date') {
    return (
      <input
        type="date"
        className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
        value={condition.value}
        onChange={(e) => updateCondition(groupId, condition.id, 'value', e.target.value)}
      />
    )
  }

  // Default text input
  return (
    <input
      type="text"
      className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
      placeholder="Enter value..."
      value={condition.value}
      onChange={(e) => updateCondition(groupId, condition.id, 'value', e.target.value)}
    />
  )
}
