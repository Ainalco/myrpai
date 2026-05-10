import React, { useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Settings,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  ArrowLeft,
  Activity,
  Calendar,
  Pencil
} from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useToast } from '@/components/ui/use-toast'
import LoadingSpinner from '@/components/ui/loading-spinner'
import ExecutionDetailsModal from '@/components/execution/ExecutionDetailsModal'
import RagSettingsPanel from '@/components/workflows/RagSettingsPanel' // ADDED IMPORT (NEW)
import { workflowApi, executionApi } from '@/lib/api'
import { formatRelativeTime, formatExecutionTime } from '@/lib/utils'

const WorkflowDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const workflowId = parseInt(id!, 10)
  const [selectedExecutionId, setSelectedExecutionId] = useState<number | null>(null)
  const [isExecutionModalOpen, setIsExecutionModalOpen] = useState(false)
  const [isEditingName, setIsEditingName] = useState(false)
  const [editName, setEditName] = useState('')
  const nameInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: workflow, isLoading: workflowLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: () => workflowApi.getById(workflowId).then(res => res.data),
    enabled: !!workflowId,
  })

  const { data: executions, isLoading: executionsLoading } = useQuery({
    queryKey: ['executions', workflowId],
    queryFn: () => executionApi.getByWorkflow(workflowId).then(res => res.data),
    enabled: !!workflowId,
  })

  const toggleActiveMutation = useMutation({
    mutationFn: (is_active: boolean) =>
      workflowApi.update(workflowId, { is_active }),
    onSuccess: (_, is_active) => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      toast({
        title: 'Success',
        description: `Workflow ${is_active ? 'activated' : 'deactivated'} successfully`,
      })
    },
    onError: () => {
      toast({
        title: 'Error',
        description: 'Failed to update workflow status',
        variant: 'destructive',
      })
    },
  })

  const renameMutation = useMutation({
    mutationFn: (name: string) => workflowApi.update(workflowId, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      setIsEditingName(false)
      toast({ title: 'Success', description: 'Workflow renamed successfully' })
    },
    onError: () => {
      setIsEditingName(false)
      toast({ title: 'Error', description: 'Failed to rename workflow', variant: 'destructive' })
    },
  })

  const handleRenameClick = () => {
    setEditName(workflow?.name || '')
    setIsEditingName(true)
    setTimeout(() => nameInputRef.current?.focus(), 0)
  }

  const handleSaveRename = () => {
    if (editName.trim() && editName.trim() !== workflow?.name) {
      renameMutation.mutate(editName.trim())
    } else {
      setIsEditingName(false)
    }
  }

  const handleNameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveRename()
    } else if (e.key === 'Escape') {
      setIsEditingName(false)
    }
  }

  if (workflowLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!workflow) {
    return (
      <div className="text-center py-12">
        <h1 className="text-2xl font-bold text-scurry-espresso mb-2">
          Workflow Not Found
        </h1>
        <p className="text-scurry-latte mb-4">
          The workflow you're looking for doesn't exist or you don't have access to it.
        </p>
        <Link to="/workflows">
          <Button variant="outline">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Workflows
          </Button>
        </Link>
      </div>
    )
  }

  const recentExecutions = executions?.slice(0, 10) || []
  const successfulExecutions = executions?.filter(e => e.status === 'completed').length || 0
  const failedExecutions = executions?.filter(e => e.status === 'failed').length || 0
  const totalExecutions = executions?.length || 0

  const successRate = totalExecutions > 0 ? Math.round((successfulExecutions / totalExecutions) * 100) : 0

  const handleExecutionClick = (executionId: number) => {
    setSelectedExecutionId(executionId)
    setIsExecutionModalOpen(true)
  }

  const handleCloseExecutionModal = () => {
    setIsExecutionModalOpen(false)
    setSelectedExecutionId(null)
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header with Light Gradient */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />

        <div className="relative z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link to="/workflows">
                <Button variant="ghost" size="sm" className="hover:bg-scurry-orange-light">
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back
                </Button>
              </Link>
              <div>
                {isEditingName ? (
                  <input
                    ref={nameInputRef}
                    type="text"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={handleNameKeyDown}
                    onBlur={handleSaveRename}
                    className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display border border-scurry-orange rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-scurry-orange"
                  />
                ) : (
                  <div className="flex items-center gap-2 group/rename">
                    <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">{workflow.name}</h1>
                    <button
                      onClick={handleRenameClick}
                      className="opacity-0 group-hover/rename:opacity-100 transition-opacity p-1 hover:bg-scurry-foam rounded"
                      title="Rename workflow"
                    >
                      <Pencil className="h-4 w-4 text-scurry-latte" />
                    </button>
                  </div>
                )}
                {workflow.description && (
                  <p className="text-sm sm:text-base text-scurry-latte mt-2">{workflow.description}</p>
                )}
                <div className="flex items-center mt-2 text-sm text-scurry-gray-muted">
                  <div className={`w-2 h-2 rounded-full mr-2 ${workflow.is_active ? 'bg-scurry-green animate-pulse' : 'bg-scurry-gray-muted'
                    }`} />
                  <span>{workflow.is_active ? 'Active' : 'Inactive'}</span>
                  <Switch
                    checked={workflow.is_active}
                    onCheckedChange={(checked) =>
                      toggleActiveMutation.mutate(checked)
                    }
                    disabled={toggleActiveMutation.isPending}
                    className="ml-2 scale-75"
                  />
                  <span className="mx-2">•</span>
                  <span>{workflow.components.length} components</span>
                  <span className="mx-2">•</span>
                  <span>Created {formatRelativeTime(new Date(workflow.created_at))}</span>
                </div>
              </div>
            </div>
            <div className="flex space-x-3">
              <Link to={`/workflows/${workflow.id}/processing`}>
                <Button variant="outline" className="hover:border-scurry-orange hover:text-scurry-orange">
                  <Settings className="h-4 w-4 mr-2" />
                  Configure
                </Button>
              </Link>
              <Button className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange shadow-md hover:shadow-lg hover:scale-105 transition-all duration-200">
                <Play className="h-4 w-4 mr-2" />
                Run Test
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="space-y-4 sm:space-y-5">

        <RagSettingsPanel
          workflowId={workflow.id}
          ragSettings={workflow.rag_settings}
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
          <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
            <div className="h-1.5 bg-gradient-to-r from-scurry-blue-text to-scurry-latte" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-3 sm:px-4">
              <CardTitle className="text-xs sm:text-sm font-medium text-scurry-latte">Total Executions</CardTitle>
              <div className="p-1.5 sm:p-2 rounded-full bg-scurry-blue-bg">
                <Activity className="h-3 w-3 sm:h-4 sm:w-4 text-scurry-blue-text" />
              </div>
            </CardHeader>
            <CardContent className="px-3 sm:px-4 pb-3 sm:pb-4">
              <div className="text-2xl sm:text-3xl font-bold text-scurry-espresso">{totalExecutions}</div>
              <p className="text-xs text-scurry-latte mt-1 hidden sm:block">
                All time runs
              </p>
            </CardContent>
          </Card>

          <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
            <div className="h-1.5 bg-gradient-to-r from-scurry-green to-scurry-energy-burst" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-3 sm:px-4">
              <CardTitle className="text-xs sm:text-sm font-medium text-scurry-latte">Success Rate</CardTitle>
              <div className="p-1.5 sm:p-2 rounded-full bg-scurry-green-light">
                <CheckCircle className="h-3 w-3 sm:h-4 sm:w-4 text-scurry-green" />
              </div>
            </CardHeader>
            <CardContent className="px-3 sm:px-4 pb-3 sm:pb-4">
              <div className="text-2xl sm:text-3xl font-bold text-scurry-espresso">{successRate}%</div>
              <p className="text-xs text-scurry-latte mt-1 hidden sm:block">
                <span className="text-scurry-green font-medium">{successfulExecutions}</span> successful
              </p>
            </CardContent>
          </Card>

          <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
            <div className="h-1.5 bg-gradient-to-r from-scurry-red to-scurry-orange" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-3 sm:px-4">
              <CardTitle className="text-xs sm:text-sm font-medium text-scurry-latte">Failed Runs</CardTitle>
              <div className="p-1.5 sm:p-2 rounded-full bg-scurry-red-light">
                <XCircle className="h-3 w-3 sm:h-4 sm:w-4 text-scurry-red" />
              </div>
            </CardHeader>
            <CardContent className="px-3 sm:px-4 pb-3 sm:pb-4">
              <div className="text-2xl sm:text-3xl font-bold text-scurry-espresso">{failedExecutions}</div>
              <p className="text-xs text-scurry-latte mt-1 hidden sm:block">
                Requires attention
              </p>
            </CardContent>
          </Card>

          <Card className="overflow-hidden border-0 shadow-md hover:shadow-lg transition-shadow">
            <div className="h-1.5 bg-gradient-to-r from-scurry-orange to-scurry-energy-burst" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 pt-4 px-3 sm:px-4">
              <CardTitle className="text-xs sm:text-sm font-medium text-scurry-latte">Components</CardTitle>
              <div className="p-1.5 sm:p-2 rounded-full bg-scurry-orange-light">
                <Settings className="h-3 w-3 sm:h-4 sm:w-4 text-scurry-orange" />
              </div>
            </CardHeader>
            <CardContent className="px-3 sm:px-4 pb-3 sm:pb-4">
              <div className="text-2xl sm:text-3xl font-bold text-scurry-espresso">{workflow.components.length}</div>
              <p className="text-xs text-scurry-latte mt-1 hidden sm:block">
                Pipeline steps
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Components Overview */}
        <Card className="border-0 shadow-md">
          <CardHeader className="border-b border-scurry-gray-border/50 bg-gradient-to-r from-scurry-foam to-white">
            <CardTitle className="text-scurry-espresso">Pipeline Components</CardTitle>
            <CardDescription className="text-scurry-latte">
              Overview of components in this workflow
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-5">
            {workflow.components.length > 0 ? (
              <div className="space-y-3">
                {workflow.components
                  .sort((a, b) => a.order - b.order)
                  .map((component, index) => (
                    <div key={component.id} className="flex items-center justify-between p-3 border border-scurry-gray-border rounded-lg hover:border-scurry-orange hover:bg-scurry-orange-light/30 hover:shadow-sm transition-all">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 bg-scurry-orange-light rounded-lg flex items-center justify-center text-sm font-medium text-scurry-orange">
                          {index + 1}
                        </div>
                        <div>
                          <h4 className="font-medium text-scurry-espresso">{component.name}</h4>
                          <p className="text-sm text-scurry-gray-muted">{component.type.replace('_', ' ')}</p>
                        </div>
                      </div>
                      {component.description && (
                        <div className="text-sm text-scurry-gray-muted max-w-md truncate">
                          {component.description}
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            ) : (
              <div className="text-center py-6">
                <Settings className="h-12 w-12 text-scurry-gray-muted mx-auto mb-4" />
                <h3 className="text-sm font-medium text-scurry-espresso mb-2">
                  No components configured
                </h3>
                <p className="text-sm text-scurry-gray-muted mb-4">
                  Add components to build your workflow pipeline
                </p>
                <Link to={`/workflows/${workflow.id}/processing`}>
                  <Button size="sm">
                    <Settings className="h-4 w-4 mr-2" />
                    Configure Workflow
                  </Button>
                </Link>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Executions */}
        <Card className="border-0 shadow-md">
          <CardHeader className="border-b border-scurry-gray-border/50 bg-gradient-to-r from-scurry-foam to-white">
            <CardTitle className="text-scurry-espresso">Recent Executions</CardTitle>
            <CardDescription className="text-scurry-latte">
              Latest workflow execution results
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-5">
            {executionsLoading ? (
              <div className="flex justify-center py-8">
                <LoadingSpinner />
              </div>
            ) : recentExecutions.length > 0 ? (
              <div className="space-y-3">
                {recentExecutions.map((execution) => (
                  <div
                    key={execution.id}
                    className="flex items-center justify-between p-3 border border-scurry-gray-border rounded-lg hover:border-scurry-orange hover:bg-scurry-orange-light/30 hover:shadow-sm cursor-pointer transition-all"
                    onClick={() => handleExecutionClick(execution.id)}
                  >
                    <div className="flex items-center space-x-3">
                      <div className={`w-3 h-3 rounded-full ${execution.status === 'completed' ? 'bg-scurry-green' :
                        execution.status === 'failed' ? 'bg-scurry-red' :
                          'bg-scurry-orange animate-pulse'
                        }`} />
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-scurry-espresso">
                            Execution #{execution.id}
                          </span>
                          <span className={`px-2 py-1 text-xs rounded-full ${execution.status === 'completed' ? 'bg-scurry-green-light text-scurry-green' :
                            execution.status === 'failed' ? 'bg-scurry-red-light text-scurry-red' :
                              'bg-scurry-orange-light text-scurry-orange'
                            }`}>
                            {execution.status}
                          </span>
                        </div>
                        <p className="text-sm text-scurry-gray-muted">
                          Started {formatRelativeTime(new Date(execution.started_at))}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      {execution.total_execution_time && (
                        <div className="text-sm text-scurry-espresso">
                          {formatExecutionTime(execution.total_execution_time)}
                        </div>
                      )}
                      {execution.error_message && (
                        <div className="text-xs text-scurry-red max-w-xs truncate">
                          {execution.error_message}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6">
                <Clock className="h-12 w-12 text-scurry-gray-muted mx-auto mb-4" />
                <h3 className="text-sm font-medium text-scurry-espresso mb-2">
                  No executions yet
                </h3>
                <p className="text-sm text-scurry-gray-muted mb-4">
                  Run this workflow to see execution history
                </p>
                <Button size="sm" className="bg-scurry-orange hover:bg-scurry-orange-hover">
                  <Play className="h-4 w-4 mr-2" />
                  Run Test
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Execution Details Modal */}
      <ExecutionDetailsModal
        workflowId={workflowId}
        executionId={selectedExecutionId}
        isOpen={isExecutionModalOpen}
        onClose={handleCloseExecutionModal}
      />
    </div>
  )
}

export default WorkflowDetailPage