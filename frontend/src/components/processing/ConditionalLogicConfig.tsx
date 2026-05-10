import React, { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { componentApi, Component } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { FIELD_DEFINITIONS, OPERATOR_OPTIONS, type FieldDefinition, type Condition } from './shared/conditionConstants'
import { renderValueInput } from './shared/ConditionValueInput'
import { OperatorToggle, DataSourceTag } from './shared/ConditionUI'

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

interface ConditionalLogicConfigProps {
  workflowId: number
  component: Component
}

interface ConditionGroup {
  id: string
  operator: 'AND' | 'OR'
  conditions: Condition[]
}

interface ConfigData {
  dataSource: string
  groups: ConditionGroup[]
  groupOperator: 'AND' | 'OR'
  action: 'continue' | 'stop'
}

// Backend format (snake_case)
interface BackendConfigData {
  data_source: string
  condition_groups: Array<{
    id: string
    logic: 'AND' | 'OR'
    conditions: Condition[]
  }>
  group_logic: 'AND' | 'OR'
  action_on_match: 'continue' | 'stop'
}

// ============================================================================
// DATA TRANSFORMATION LAYER
// ============================================================================

function transformToBackendFormat(frontendConfig: ConfigData): BackendConfigData {
  return {
    data_source: frontendConfig.dataSource,
    condition_groups: frontendConfig.groups.map(group => ({
      id: group.id,
      logic: group.operator,
      conditions: group.conditions
    })),
    group_logic: frontendConfig.groupOperator,
    action_on_match: frontendConfig.action
  }
}

function transformFromBackendFormat(backendConfig: any): ConfigData {
  if (!backendConfig) {
    return {
      dataSource: 'pipedrive',
      groups: [],
      groupOperator: 'AND',
      action: 'continue'
    }
  }

  return {
    dataSource: backendConfig.data_source || 'pipedrive',
    groups: (backendConfig.condition_groups || []).map((group: any) => ({
      id: group.id,
      operator: group.logic || 'AND',
      conditions: group.conditions || []
    })),
    groupOperator: backendConfig.group_logic || 'AND',
    action: backendConfig.action_on_match || 'continue'
  }
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

const ConditionalLogicConfig: React.FC<ConditionalLogicConfigProps> = ({
  workflowId,
  component
}) => {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [config, setConfig] = useState<ConfigData>({
    dataSource: 'pipedrive',
    groups: [{
      id: '1',
      operator: 'AND',
      conditions: [{ id: '1', field: '', operator: 'equals', value: '' }]
    }],
    groupOperator: 'AND',
    action: 'continue'
  })

  const [fieldDefinitions, setFieldDefinitions] = useState<FieldDefinition[]>(FIELD_DEFINITIONS)

  // Fetch Pipedrive stages
  const { data: stagesData } = useQuery({
    queryKey: ['pipedrive-stages'],
    queryFn: async () => {
      const response = await componentApi.getPipedriveStages()
      return response.data
    },
    enabled: config.dataSource === 'pipedrive'
  })

  // Fetch Pipedrive users
  const { data: usersData } = useQuery({
    queryKey: ['pipedrive-users'],
    queryFn: async () => {
      const response = await componentApi.getPipedriveUsers()
      return response.data
    },
    enabled: config.dataSource === 'pipedrive'
  })

  // Fetch Pipedrive currencies
  const { data: currenciesData } = useQuery({
    queryKey: ['pipedrive-currencies'],
    queryFn: async () => {
      const response = await componentApi.getPipedriveCurrencies()
      return response.data
    },
    enabled: config.dataSource === 'pipedrive'
  })

  // Update field definitions when Pipedrive data loads
  useEffect(() => {
    if (stagesData?.stages_by_pipeline) {
      setFieldDefinitions(prev => prev.map(field => {
        if (field.value === 'stage') {
          const grouped: Record<string, Array<{ value: string; label: string }>> = {}
          Object.entries(stagesData.stages_by_pipeline).forEach(([pipelineId, pipelineData]: [string, any]) => {
            const pipelineName = pipelineData.pipeline_name
            grouped[pipelineName] = pipelineData.stages.map((stage: any) => ({
              value: stage.id,
              label: stage.name
            }))
          })
          return { ...field, grouped_options: grouped }
        }
        return field
      }))
    }
  }, [stagesData])

  useEffect(() => {
    if (usersData?.users) {
      setFieldDefinitions(prev => prev.map(field => {
        if (field.value === 'owner_name') {
          return { ...field, options: usersData.users }
        }
        return field
      }))
    }
  }, [usersData])

  useEffect(() => {
    if (currenciesData?.currencies) {
      setFieldDefinitions(prev => prev.map(field => {
        if (field.value === 'currency') {
          return { ...field, options: currenciesData.currencies }
        }
        return field
      }))
    }
  }, [currenciesData])

  // Load configuration from component
  useEffect(() => {
    if (component.configuration) {
      const transformed = transformFromBackendFormat(component.configuration)
      setConfig(transformed)
    }
  }, [component])

  // Save mutation
  const updateConfigMutation = useMutation({
    mutationFn: (backendConfig: BackendConfigData) =>
      componentApi.updateConfig(component.id, backendConfig),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      toast({
        title: "Configuration Saved! 🎉",
        description: "Your conditional logic rules have been updated successfully.",
      })
    },
    onError: (error: any) => {
      toast({
        title: "Save Failed",
        description: error.response?.data?.detail || "Failed to save configuration",
        variant: "destructive",
      })
    }
  })

  // Handlers
  const addCondition = (groupId: string) => {
    setConfig(prev => ({
      ...prev,
      groups: prev.groups.map(group =>
        group.id === groupId
          ? {
              ...group,
              conditions: [
                ...group.conditions,
                { id: Date.now().toString(), field: '', operator: 'equals', value: '' }
              ]
            }
          : group
      )
    }))
  }

  const removeCondition = (groupId: string, conditionId: string) => {
    setConfig(prev => ({
      ...prev,
      groups: prev.groups.map(group =>
        group.id === groupId
          ? {
              ...group,
              conditions: group.conditions.filter(c => c.id !== conditionId)
            }
          : group
      )
    }))
  }

  const updateCondition = (groupId: string, conditionId: string, field: keyof Condition, value: string) => {
    setConfig(prev => ({
      ...prev,
      groups: prev.groups.map(group =>
        group.id === groupId
          ? {
              ...group,
              conditions: group.conditions.map(c =>
                c.id === conditionId ? { ...c, [field]: value } : c
              )
            }
          : group
      )
    }))
  }

  const addGroup = () => {
    setConfig(prev => ({
      ...prev,
      groups: [
        ...prev.groups,
        {
          id: Date.now().toString(),
          operator: 'AND',
          conditions: [
            { id: (Date.now() + 1).toString(), field: '', operator: 'equals', value: '' }
          ]
        }
      ]
    }))
  }

  const removeGroup = (groupId: string) => {
    if (config.groups.length <= 1) return
    setConfig(prev => ({
      ...prev,
      groups: prev.groups.filter(g => g.id !== groupId)
    }))
  }

  const toggleGroupOperator = (groupId: string) => {
    setConfig(prev => ({
      ...prev,
      groups: prev.groups.map(group =>
        group.id === groupId
          ? { ...group, operator: group.operator === 'AND' ? 'OR' : 'AND' }
          : group
      )
    }))
  }

  const toggleGlobalOperator = () => {
    setConfig(prev => ({
      ...prev,
      groupOperator: prev.groupOperator === 'AND' ? 'OR' : 'AND'
    }))
  }

  const isConfigComplete = (): boolean => {
    return config.groups.every(group =>
      group.conditions.every(c =>
        c.field &&
        c.operator &&
        (c.value || c.operator === 'is_empty' || c.operator === 'is_not_empty')
      )
    )
  }

  const handleSave = async () => {
    const backendConfig = transformToBackendFormat(config)
    await updateConfigMutation.mutateAsync(backendConfig)
  }

  const getOperatorExplanation = (op: string) => {
    const explanations: Record<string, string> = {
      'AND': '🔗 ALL conditions must match (picky squirrel mode)',
      'OR': '🎲 ANY condition can match (flexible squirrel mode)',
    }
    return explanations[op]
  }

  const getFieldDefinition = (fieldValue: string): FieldDefinition | undefined => {
    return fieldDefinitions.find(f => f.value === fieldValue)
  }

  return (
    <div className="space-y-5">
      {/* Data Source Section */}
      <div className="bg-white rounded-xl p-6 shadow-[0_2px_8px_rgba(62,39,35,0.06)] border border-scurry-foam">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl">📊</span>
          <h3 className="text-base font-semibold text-scurry-espresso">Data Source</h3>
          <span className="text-sm text-scurry-latte ml-auto">Where should we look?</span>
        </div>
        <div>
          <label className="block text-sm font-semibold text-scurry-espresso mb-2">
            Select CRM/Data Source
          </label>
          <div className="relative">
            <select
              className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
              value={config.dataSource}
              onChange={(e) => setConfig(prev => ({ ...prev, dataSource: e.target.value }))}
            >
              <option value="pipedrive">🟢 Pipedrive</option>
              <option value="hubspot">🟠 HubSpot (Coming Soon)</option>
              <option value="salesforce">🔵 Salesforce (Coming Soon)</option>
            </select>
            <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">▼</span>
          </div>
        </div>
      </div>

      {/* Rules Section */}
      <div className="bg-white rounded-xl p-6 shadow-[0_2px_8px_rgba(62,39,35,0.06)] border border-scurry-foam">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl">⚡</span>
          <h3 className="text-base font-semibold text-scurry-espresso">Conditional Logic Rules</h3>
          <DataSourceTag source={config.dataSource} />
        </div>

        {/* Global Operator */}
        {config.groups.length > 1 && (
          <div className="flex items-center gap-3 px-4 py-3 bg-scurry-foam/40 rounded-lg mb-4">
            <span className="text-sm font-medium text-scurry-espresso">Groups are combined with:</span>
            <OperatorToggle
              value={config.groupOperator}
              onChange={toggleGlobalOperator}
              size="large"
            />
            <span className="text-xs text-scurry-latte ml-auto">
              {getOperatorExplanation(config.groupOperator)}
            </span>
          </div>
        )}

        {/* Condition Groups */}
        <div className="flex flex-col gap-0">
          {config.groups.map((group, groupIndex) => (
            <React.Fragment key={group.id}>
              {/* Group Connector */}
              {groupIndex > 0 && (
                <div className="flex items-center justify-center py-2">
                  <div className="flex-1 h-0.5 bg-scurry-foam"></div>
                  <span className="px-4 py-1 bg-scurry-foam rounded-full text-xs font-bold text-scurry-orange mx-3">
                    {config.groupOperator}
                  </span>
                  <div className="flex-1 h-0.5 bg-scurry-foam"></div>
                </div>
              )}

              {/* Group Card */}
              <div className="bg-scurry-foam/40 border border-scurry-foam rounded-xl p-4 transition-all hover:border-scurry-orange hover:shadow-[0_4px_12px_rgba(255,87,34,0.1)]">
                <div className="flex justify-between items-center mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-scurry-espresso">Group {groupIndex + 1}</span>
                    {group.conditions.length > 1 && (
                      <OperatorToggle
                        value={group.operator}
                        onChange={() => toggleGroupOperator(group.id)}
                        size="small"
                      />
                    )}
                  </div>
                  {config.groups.length > 1 && (
                    <button
                      className="px-2 py-1 bg-transparent border border-scurry-red-light rounded-md text-sm opacity-60 hover:opacity-100 transition-all"
                      onClick={() => removeGroup(group.id)}
                      title="Remove this group"
                    >
                      🗑️
                    </button>
                  )}
                </div>

                {/* Conditions */}
                <div className="flex flex-col gap-0">
                  {group.conditions.map((condition, condIndex) => (
                    <div key={condition.id} className="grid grid-cols-[1fr_160px_1fr_32px] gap-2 items-center py-2 relative">
                      {/* Condition Connector */}
                      {condIndex > 0 && (
                        <div className="absolute -left-6 top-1/2 -translate-y-1/2">
                          <span className="text-xs font-bold text-scurry-gray-muted bg-scurry-gray-light px-1.5 py-0.5 rounded">
                            {group.operator}
                          </span>
                        </div>
                      )}

                      {/* Field Select */}
                      <div className="relative min-w-0">
                        <select
                          className={`w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10 ${!condition.field ? 'text-scurry-latte' : 'text-scurry-espresso'}`}
                          value={condition.field}
                          onChange={(e) => updateCondition(group.id, condition.id, 'field', e.target.value)}
                        >
                          <option value="">Select field...</option>
                          {fieldDefinitions.map(f => (
                            <option key={f.value} value={f.value}>
                              {f.icon} {f.label}
                            </option>
                          ))}
                        </select>
                        <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">▼</span>
                      </div>

                      {/* Operator Select */}
                      <div className="relative min-w-0">
                        <select
                          className="w-full px-3.5 py-2.5 text-sm border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                          value={condition.operator}
                          onChange={(e) => updateCondition(group.id, condition.id, 'operator', e.target.value)}
                        >
                          {OPERATOR_OPTIONS.map(op => (
                            <option key={op.value} value={op.value}>
                              {op.symbol} {op.label}
                            </option>
                          ))}
                        </select>
                        <span className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">▼</span>
                      </div>

                      {/* Value Input */}
                      <div className="min-w-0">
                        {condition.operator !== 'is_empty' && condition.operator !== 'is_not_empty' ? (
                          renderValueInput(condition, group.id, fieldDefinitions, updateCondition)
                        ) : (
                          <div className="px-3.5 py-3 bg-scurry-gray-light rounded-lg text-sm text-scurry-gray-muted text-center">
                            <span>✨ No value needed</span>
                          </div>
                        )}
                      </div>

                      {/* Remove Condition */}
                      {group.conditions.length > 1 && (
                        <button
                          className="w-7 h-7 flex items-center justify-center bg-transparent border border-scurry-gray-border rounded-md text-lg text-scurry-gray-muted hover:text-scurry-red hover:border-scurry-red transition-all"
                          onClick={() => removeCondition(group.id, condition.id)}
                          title="Remove condition"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                {/* Add Condition Button */}
                <button
                  onClick={() => addCondition(group.id)}
                  className="mt-3 w-full py-2 border border-dashed border-scurry-gray-muted rounded-lg bg-transparent text-scurry-latte text-sm flex items-center justify-center gap-2 cursor-pointer transition-all hover:border-scurry-orange hover:text-scurry-orange hover:bg-scurry-orange/5"
                >
                  <span className="text-lg leading-none">+</span>
                  Add Condition
                </button>
              </div>
            </React.Fragment>
          ))}
        </div>

        {/* Add Group Button */}
        <button
          onClick={addGroup}
          className="group mt-6 w-full py-4 border border-dashed border-scurry-gray-muted rounded-xl bg-transparent cursor-pointer transition-all hover:border-scurry-orange hover:bg-scurry-orange/5 flex flex-col items-center gap-2"
        >
          <div className="w-8 h-8 bg-scurry-gray-border rounded-full flex items-center justify-center text-scurry-latte text-xl transition-colors group-hover:bg-scurry-orange group-hover:text-white">
            +
          </div>
          <span className="text-sm font-medium text-scurry-latte">Add Condition Group</span>
          <span className="text-xs text-scurry-gray-muted">Create another set of rules</span>
        </button>
      </div>

      {/* Action Section */}
      <div className="bg-scurry-foam/40 rounded-xl px-6 py-5 border border-scurry-foam">
        <div className="flex items-center gap-2 mb-4">
          <span className="text-xl">🎯</span>
          <span className="text-sm font-semibold text-scurry-espresso">When conditions are met:</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <ActionCard
            selected={config.action === 'continue'}
            onClick={() => setConfig(prev => ({ ...prev, action: 'continue' }))}
            icon="✅"
            title="Continue Pipeline"
            description="Execute next components when conditions match"
            color="#4CAF50"
          />
          <ActionCard
            selected={config.action === 'stop'}
            onClick={() => setConfig(prev => ({ ...prev, action: 'stop' }))}
            icon="🛑"
            title="Stop Pipeline"
            description="End pipeline execution when conditions match"
            color="#F44336"
          />
        </div>
      </div>

    </div>
  )
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

// DataSourceTag and OperatorToggle imported from ./shared/ConditionUI

const ActionCard: React.FC<{
  selected: boolean
  onClick: () => void
  icon: string
  title: string
  description: string
  color: string
}> = ({ selected, onClick, icon, title, description, color }) => (
  <button
    className={`flex items-center gap-3.5 p-4 bg-white rounded-xl cursor-pointer transition-all text-left relative ${
      selected
        ? 'border-2 shadow-sm'
        : 'border border-scurry-latte/20 hover:border-scurry-latte/40'
    }`}
    style={selected ? {
      borderColor: color,
      backgroundColor: `${color}08`
    } : {}}
    onClick={onClick}
  >
    <div
      className={`w-11 h-11 flex items-center justify-center rounded-lg text-xl flex-shrink-0 ${
        !selected ? 'bg-scurry-gray-border text-scurry-latte' : ''
      }`}
      style={selected ? {
        backgroundColor: color,
        color: 'white'
      } : {}}
    >
      {icon}
    </div>
    <div className="flex-1 min-w-0">
      <div
        className={`text-sm font-semibold mb-0.5 ${!selected ? 'text-scurry-espresso' : ''}`}
        style={selected ? { color } : {}}
      >
        {title}
      </div>
      <div className="text-xs text-scurry-latte">{description}</div>
    </div>
    {selected && (
      <div
        className="absolute -top-2 -right-2 w-6 h-6 flex items-center justify-center rounded-full text-white text-xs font-bold"
        style={{ backgroundColor: color }}
      >
        ✓
      </div>
    )}
  </button>
)

export default ConditionalLogicConfig
