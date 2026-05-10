// Shared sub-components for condition-based UIs.
// Used by ConditionalLogicConfig (full groups) and EmailConfig (pre-send check groups).

import React from 'react'

export const DataSourceTag: React.FC<{ source: string }> = ({ source }) => (
  <div className="flex items-center gap-1.5 px-2.5 py-1 bg-scurry-foam rounded-xl text-xs font-medium text-scurry-latte capitalize">
    <span className="text-xs">
      {source === 'pipedrive' && '🟢'}
      {source === 'hubspot' && '🟠'}
      {source === 'salesforce' && '🔵'}
    </span>
    {source}
  </div>
)

export const OperatorToggle: React.FC<{
  value: 'AND' | 'OR'
  onChange: () => void
  size: 'small' | 'large'
}> = ({ value, onChange, size }) => (
  <button
    className={`flex items-center gap-1 border-0 rounded-md font-bold cursor-pointer transition-all ${
      size === 'large' ? 'px-3.5 py-1.5 text-sm' : 'px-2.5 py-1 text-xs'
    } ${
      value === 'AND'
        ? 'bg-scurry-blue-bg text-scurry-blue-text hover:bg-scurry-blue-bg/80'
        : 'bg-scurry-orange-light text-scurry-orange-hover hover:bg-scurry-orange-light/80'
    }`}
    onClick={onChange}
    title={`Click to switch to ${value === 'AND' ? 'OR' : 'AND'}`}
  >
    {value}
    <span className="text-xs opacity-60">↕</span>
  </button>
)
