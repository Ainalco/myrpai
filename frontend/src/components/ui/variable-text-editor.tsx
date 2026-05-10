import React, { useState, useRef, useEffect } from 'react'
import { Sparkles, Zap, ChevronDown, Command, Layers, Edit, Copy, Eye, Lightbulb } from 'lucide-react'
import { Button } from './button'

interface ExtractedVariable {
  id: number
  variable_name: string
  variable_key: string
  variable_value: any
  data_type: string
  // Component-level variable fields
  source_component_name?: string
  source_component_type?: string
  is_component_level?: boolean
}

interface VariableTextEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  workflowId?: number
  componentId?: number  // For fetching component-level variables
  className?: string
  rows?: number
  previewVariables?: ExtractedVariable[]
  // React Hook Form support
  name?: string
  register?: any
  // Optional features
  showCopyButton?: boolean
  enablePreview?: boolean
  // For controlled preview mode
  isPreviewMode?: boolean
  onPreviewToggle?: () => void
}

interface VariableDropdownProps {
  variables: ExtractedVariable[]
  onSelect: (variable: ExtractedVariable) => void
  onClose: () => void
  filter: string
}

const VariableDropdown: React.FC<VariableDropdownProps> = ({
  variables,
  onSelect,
  onClose,
  filter
}) => {
  const [selectedIndex, setSelectedIndex] = useState(0)
  const dropdownRef = useRef<HTMLDivElement>(null)
  
  // Filter variables based on the current input
  const filteredVariables = variables.filter(variable => {
    // If filter is empty (just typed "/"), show all variables
    if (!filter.trim()) {
      return true
    }
    // Otherwise filter by name
    return variable.variable_name.toLowerCase().includes(filter.toLowerCase())
  })
  
  
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'ArrowDown') {
        event.preventDefault()
        setSelectedIndex(prev => Math.min(prev + 1, filteredVariables.length - 1))
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        setSelectedIndex(prev => Math.max(prev - 1, 0))
      } else if (event.key === 'Enter') {
        event.preventDefault()
        if (filteredVariables[selectedIndex]) {
          onSelect(filteredVariables[selectedIndex])
        }
      } else if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [filteredVariables, selectedIndex, onSelect, onClose])

  useEffect(() => {
    setSelectedIndex(0) // Reset selection when filter changes
  }, [filter])

  const formatPreview = (value: any, dataType: string) => {
    if (value === null || value === undefined) return '[No data]'
    
    if (dataType === 'array' && Array.isArray(value)) {
      return value.length > 0 ? `${value.slice(0, 2).join(', ')}${value.length > 2 ? '...' : ''}` : '[]'
    }
    
    if (dataType === 'boolean') {
      return value ? 'Yes' : 'No'
    }
    
    const str = String(value)
    return str.length > 30 ? str.substring(0, 30) + '...' : str
  }

  if (filteredVariables.length === 0) {
    return (
      <div
        ref={dropdownRef}
        className="min-w-80 bg-white border border-gray-100 rounded-xl shadow-2xl backdrop-blur-sm p-4"
      >
        <div className="text-center text-gray-400 text-sm font-medium">
          No variables found for "{filter}"
        </div>
        <div className="text-center text-gray-300 text-xs mt-1">
          Try typing a different variable name
        </div>
      </div>
    )
  }

  return (
    <div
      ref={dropdownRef}
      className="min-w-96 bg-white/95 backdrop-blur-xl border border-gray-100 rounded-2xl shadow-2xl ring-1 ring-black/5 overflow-hidden"
    >
      <div className="p-4 bg-gradient-to-r from-indigo-50 via-blue-50 to-cyan-50 border-b border-gray-100/50">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-blue-600 rounded-lg flex items-center justify-center">
              <Zap className="h-4 w-4 text-white" />
            </div>
            <div>
              <div className="font-semibold text-gray-800 text-sm">Available Variables</div>
              <div className="text-xs text-gray-500">Insert dynamic content</div>
            </div>
          </div>
          <div className="text-xs text-gray-400 font-mono bg-white/50 px-2 py-1 rounded-md">
            {filteredVariables.length} found
          </div>
        </div>
      </div>
      
      <div className="max-h-72 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-200 scrollbar-track-transparent">
        {filteredVariables.map((variable, index) => {
          const isPreview = variable.id === -1 || variable.variable_value === undefined
          return (
            <div
              key={variable.id || `preview-${variable.variable_name}`}
              className={`p-4 cursor-pointer transition-all duration-200 border-l-4 ${
                variable.is_component_level
                  ? index === selectedIndex
                    ? 'bg-gradient-to-r from-purple-50 to-pink-50 border-l-purple-500 shadow-md'
                    : 'hover:bg-gradient-to-r hover:from-purple-25 hover:to-pink-25 border-l-transparent hover:border-l-purple-300'
                  : index === selectedIndex
                    ? 'bg-gradient-to-r from-indigo-50 to-blue-50 border-l-indigo-500 shadow-sm'
                    : 'hover:bg-gray-25 border-l-transparent hover:border-l-gray-200'
              }`}
              onClick={() => onSelect(variable)}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2">
                    {variable.is_component_level ? (
                      // Beautiful display for component-level variables
                      <div className="flex items-center gap-2">
                        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-pink-600 shadow-sm">
                          <Layers className="w-4 h-4 text-white" />
                        </div>
                        <div className="font-semibold text-lg text-gray-900">
                          {variable.source_component_name}
                        </div>
                        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-purple-100 to-pink-100 text-purple-700 border border-purple-200 shadow-sm">
                          Component Output
                        </span>
                      </div>
                    ) : (
                      // Regular display for field-level variables
                      <>
                        <div className={`font-semibold truncate font-mono ${isPreview ? 'text-gray-700' : 'text-gray-900'}`}>
                          {`{{${variable.variable_name}}}`}
                        </div>
                        {isPreview && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gradient-to-r from-blue-100 to-indigo-100 text-indigo-700 border border-indigo-200">
                            <Sparkles className="w-3 h-3 mr-1" />
                            Preview
                          </span>
                        )}
                      </>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-1.5 leading-relaxed">
                    {isPreview
                      ? 'Will be populated after the workflow runs'
                      : variable.is_component_level
                        ? `Inserts all outputs from this component as JSON (${variable.source_component_type})`
                        : formatPreview(variable.variable_value, variable.data_type)
                    }
                  </div>
                </div>
                <div className="ml-3 flex-shrink-0">
                  <div className={`text-xs px-3 py-1.5 rounded-full font-medium ${
                    isPreview
                      ? 'bg-gradient-to-r from-blue-100 to-indigo-100 text-indigo-700 border border-indigo-200'
                      : variable.is_component_level
                        ? 'bg-gradient-to-r from-purple-100 to-pink-100 text-purple-700 border border-purple-200'
                        : 'bg-gray-100 text-gray-700 border border-gray-200'
                  }`}>
                    {variable.data_type}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
      
      <div className="p-3 bg-gradient-to-r from-gray-50 to-slate-50 border-t border-gray-100/50">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center space-x-4 text-gray-500">
            <div className="flex items-center space-x-1">
              <div className="w-4 h-4 bg-gray-200 rounded flex items-center justify-center">
                <ChevronDown className="w-2.5 h-2.5 rotate-180" />
              </div>
              <span>Navigate</span>
            </div>
            <div className="flex items-center space-x-1">
              <div className="w-4 h-4 bg-gray-200 rounded flex items-center justify-center">
                <Command className="w-2.5 h-2.5" />
              </div>
              <span>Select</span>
            </div>
          </div>
          <div className="text-gray-400">
            Press Esc to close
          </div>
        </div>
      </div>
    </div>
  )
}

const VariableTextEditor: React.FC<VariableTextEditorProps> = ({
  value,
  onChange,
  placeholder,
  workflowId,
  componentId,
  className = '',
  rows = 4,
  previewVariables = [],
  name,
  register,
  showCopyButton = false,
  enablePreview = false,
  isPreviewMode: externalIsPreviewMode,
  onPreviewToggle: externalOnPreviewToggle
}) => {
  const [dbVariables, setDbVariables] = useState<ExtractedVariable[]>([])
  const [showDropdown, setShowDropdown] = useState(false)
  const [variableFilter, setVariableFilter] = useState('')
  const [cursorPosition, setCursorPosition] = useState(0)
  const [internalIsPreviewMode, setInternalIsPreviewMode] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Use external preview mode if provided, otherwise use internal
  const isPreviewMode = externalIsPreviewMode !== undefined ? externalIsPreviewMode : internalIsPreviewMode
  const handlePreviewToggle = externalOnPreviewToggle || (() => setInternalIsPreviewMode(!internalIsPreviewMode))

  // Combine database variables with preview variables
  const variables = [...dbVariables, ...previewVariables]
  
  
  // Fetch variables when workflow or component changes
  useEffect(() => {
    if (componentId || workflowId) {
      fetchVariables()
    }
  }, [workflowId, componentId])
  
  const fetchVariables = async () => {
    try {
      const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:9000'
      let response

      // Prefer component-level API if componentId is provided
      if (componentId) {
        response = await fetch(`${API_BASE_URL}/components/${componentId}/available-variables`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        })

        if (response.ok) {
          const data = await response.json()
          // Transform component-level API response to ExtractedVariable format
          const transformedVariables = data.available_variables.map((v: any) => ({
            id: v.source_component_id || -1,
            variable_name: v.value,
            variable_key: v.value,
            variable_value: undefined, // Not available in component-level API
            data_type: v.variable_type,
            source_component_name: v.source_component_name,
            source_component_type: v.source_component_type,
            is_component_level: v.is_component_level
          }))
          setDbVariables(transformedVariables)
        }
      } else if (workflowId) {
        // Fall back to workflow-level API
        response = await fetch(`${API_BASE_URL}/workflows/${workflowId}/variables`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`
          }
        })

        if (response.ok) {
          const data = await response.json()
          setDbVariables(data)
        }
      }
    } catch (error) {
      console.error('Failed to fetch variables:', error)
    }
  }
  
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value
    const cursorPos = e.target.selectionStart

    onChange(newValue)
    setCursorPosition(cursorPos)

    // Check for {{ trigger
    const textBeforeCursor = newValue.slice(0, cursorPos)
    const lastDoubleBraceIndex = textBeforeCursor.lastIndexOf('{{')

    if (lastDoubleBraceIndex !== -1) {
      const afterBraces = textBeforeCursor.slice(lastDoubleBraceIndex + 2)

      // Check if we've closed the braces with }}
      const hasClosingBraces = afterBraces.includes('}}')

      // Only show dropdown if there's no closing braces and no newline
      if (!hasClosingBraces && !afterBraces.includes('\n')) {
        setVariableFilter(afterBraces)
        setShowDropdown(true)
      } else {
        setShowDropdown(false)
      }
    } else {
      setShowDropdown(false)
    }
  }

  const handleVariableSelect = (variable: ExtractedVariable) => {
    if (!textareaRef.current) return

    const textarea = textareaRef.current
    const textBeforeCursor = value.slice(0, cursorPosition)
    const textAfterCursor = value.slice(cursorPosition)
    const lastDoubleBraceIndex = textBeforeCursor.lastIndexOf('{{')

    if (lastDoubleBraceIndex !== -1) {
      const beforeBraces = value.slice(0, lastDoubleBraceIndex)
      const variablePlaceholder = `{{${variable.variable_name}}}`
      const newValue = beforeBraces + variablePlaceholder + textAfterCursor

      onChange(newValue)
      setShowDropdown(false)

      // Set cursor after the inserted variable
      setTimeout(() => {
        const newCursorPos = beforeBraces.length + variablePlaceholder.length
        textarea.setSelectionRange(newCursorPos, newCursorPos)
        textarea.focus()
      }, 0)
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (showDropdown && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === 'Escape')) {
      // Let the dropdown handle these keys
      return
    }
  }

  const handleCopy = () => {
    if (value) {
      navigator.clipboard.writeText(value)
    }
  }

  // Render preview mode with variable highlighting
  const renderPreviewWithVariables = (text: string) => {
    if (!text) return null

    const parts = text.split(/(\{\{[^}]+\}\})/g)
    return (
      <div className="text-sm text-gray-800 whitespace-pre-wrap font-mono leading-relaxed">
        {parts.map((part, i) => {
          if (part.match(/\{\{[^}]+\}\}/)) {
            const varName = part.replace(/\{\{|\}\}/g, '').trim()
            const isComponentLevel = varName.startsWith('component:')

            if (isComponentLevel) {
              const componentName = varName.substring('component:'.length).trim()
              return (
                <span
                  key={i}
                  className="inline-flex items-center gap-1.5 mx-1 my-0.5 px-3 py-1.5 bg-gradient-to-r from-purple-500 via-purple-600 to-pink-600 text-white rounded-lg shadow-md font-bold text-xs hover:from-purple-600 hover:via-purple-700 hover:to-pink-700 hover:shadow-lg transition-all border border-purple-400/30"
                  title={`Component Output: ${componentName} (all data as JSON)`}
                >
                  <Layers className="h-4 w-4" />
                  {componentName}
                </span>
              )
            }

            return (
              <span
                key={i}
                className="inline-flex items-center gap-1 mx-1 my-0.5 px-2.5 py-1 bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-md shadow-sm font-semibold text-xs hover:from-blue-600 hover:to-blue-700 transition-all"
                title={`Variable: ${varName}`}
              >
                <Layers className="h-3.5 w-3.5" />
                {varName}
              </span>
            )
          }
          return (
            <span key={i} className="text-gray-800">
              {part}
            </span>
          )
        })}
      </div>
    )
  }

  // Prepare textarea props for RHF or direct control
  const textareaProps = register && name
    ? {
        ...register(name, {
          onChange: handleInputChange
        }),
        ref: (e: HTMLTextAreaElement | null) => {
          register(name).ref(e)
          textareaRef.current = e
        }
      }
    : {
        value,
        onChange: handleInputChange,
        ref: textareaRef
      }

  return (
    <div className="relative space-y-2">
      {/* Action buttons row */}
      {(showCopyButton || enablePreview) && (
        <div className="flex items-center justify-end space-x-2">
          {enablePreview && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handlePreviewToggle}
            >
              {isPreviewMode ? (
                <>
                  <Edit className="h-3 w-3 mr-1" />
                  Edit
                </>
              ) : (
                <>
                  <Eye className="h-3 w-3 mr-1" />
                  Preview
                </>
              )}
            </Button>
          )}
          {showCopyButton && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopy}
            >
              <Copy className="h-3 w-3 mr-1" />
              Copy
            </Button>
          )}
        </div>
      )}

      {/* Preview mode or Edit mode */}
      {isPreviewMode ? (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 min-h-[100px]">
          {value ? (
            renderPreviewWithVariables(value)
          ) : (
            <p className="text-sm text-gray-500 italic">
              No content configured. Click Edit to add.
            </p>
          )}
        </div>
      ) : (
        <div className="relative">
          {/* Textarea */}
          <textarea
            {...textareaProps}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || "Type {{ to insert variables..."}
            rows={rows}
            className={`w-full p-4 border border-gray-200 rounded-lg bg-white
                       focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:bg-white
                       hover:border-gray-300
                       transition-all duration-200 resize-none
                       placeholder:text-gray-400
                       text-gray-800 leading-relaxed font-mono text-sm
                       ${className}`}
            style={{
              minHeight: rows * 24 + 32
            }}
          />

          {/* Hint text and variables indicator */}
          <div className="flex items-start justify-between gap-2 mt-2">
            <p className="text-xs text-gray-500">
              Type <code className="bg-gray-100 px-1 rounded">{"{{"}</code> to see available variables from previous components
            </p>
            {variables.length > 0 && (
              <div className="text-xs text-green-600 flex items-center gap-1 flex-shrink-0">
                <Lightbulb className="h-3 w-3" />
                {variables.length} variables available
              </div>
            )}
          </div>

          {/* Variable dropdown - positioned below textarea */}
          {showDropdown && (
            <div className="absolute left-0 right-0 z-50 mt-1" style={{ top: '100%' }}>
              <VariableDropdown
                variables={variables}
                onSelect={handleVariableSelect}
                onClose={() => setShowDropdown(false)}
                filter={variableFilter}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default VariableTextEditor