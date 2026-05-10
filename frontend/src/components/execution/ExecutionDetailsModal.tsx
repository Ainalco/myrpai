import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle 
} from '@/components/ui/dialog'
import {
  CheckCircle,
  XCircle,
  Clock,
  Play,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Database,
  ArrowRight,
  Calendar,
  Timer,
  FileText,
  Zap,
  Activity
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { executionApi, workflowApi, Execution } from '@/lib/api'
import { formatRelativeTime, formatExecutionTime } from '@/lib/utils'
import RagPanel from '@/components/processing/RagPanel'

interface ExecutionDetailsModalProps {
  workflowId: number
  executionId: number | null
  isOpen: boolean
  onClose: () => void
}

interface ComponentExecution {
  id: number
  component_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at?: string
  completed_at?: string
  execution_time?: number
  input_data?: any
  output_data?: any
  error_message?: string
}

const ExecutionDetailsModal: React.FC<ExecutionDetailsModalProps> = ({
  workflowId,
  executionId,
  isOpen,
  onClose
}) => {
  const { data: execution, isLoading: executionLoading } = useQuery({
    queryKey: ['execution', workflowId, executionId],
    queryFn: async () => {
      if (!executionId) return null
      const response = await executionApi.getById(workflowId, executionId)
      return response.data
    },
    enabled: isOpen && !!executionId
  })

  const { data: workflow, isLoading: workflowLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: async () => {
      const response = await workflowApi.getById(workflowId)
      return response.data
    },
    enabled: isOpen && !!workflowId
  })

  const isLoading = executionLoading || workflowLoading

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-scurry-green" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-scurry-red" />
      case 'running':
        return <Play className="h-4 w-4 text-scurry-orange animate-pulse" />
      default:
        return <Clock className="h-4 w-4 text-scurry-gray-muted" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-scurry-green-light text-scurry-green'
      case 'failed':
        return 'bg-scurry-red-light text-scurry-red'
      case 'running':
        return 'bg-scurry-orange-light text-scurry-orange'
      default:
        return 'bg-scurry-gray-light text-scurry-espresso'
    }
  }

  const formatJsonData = (data: any) => {
    if (!data) return 'No data'
    return JSON.stringify(data, null, 2)
  }

  const ComponentExecutionDetails: React.FC<{ compExec: ComponentExecution; index: number }> = ({ compExec, index }) => {
    const [isExpanded, setIsExpanded] = React.useState(false)
    
    // Find the component details from workflow
    const component = workflow?.components.find(c => c.id === compExec.component_id)
    const componentName = component?.name || `Component ${compExec.component_id}`
    const componentType = component?.type || 'unknown'

    return (
      <Card className="mb-4">
        <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-scurry-foam transition-colors">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 bg-scurry-orange-light rounded-full flex items-center justify-center text-sm font-medium text-scurry-orange">
                    {index + 1}
                  </div>
                  <div>
                    <CardTitle className="text-sm flex items-center space-x-2">
                      {getStatusIcon(compExec.status)}
                      <span>{componentName}</span>
                      <Badge variant="outline" className="text-xs">
                        {componentType.replace('_', ' ')}
                      </Badge>
                    </CardTitle>
                    <div className="flex items-center space-x-4 text-xs text-scurry-gray-muted mt-1">
                      <span className={`px-2 py-1 rounded-full ${getStatusColor(compExec.status)}`}>
                        {compExec.status}
                      </span>
                      {compExec.execution_time && (
                        <span className="flex items-center">
                          <Timer className="h-3 w-3 mr-1" />
                          {formatExecutionTime(compExec.execution_time)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  {compExec.error_message && (
                    <AlertTriangle className="h-4 w-4 text-scurry-red" />
                  )}
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </div>
              </div>
            </CardHeader>
          </CollapsibleTrigger>

          <CollapsibleContent>
            <CardContent className="pt-0">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Timing Information */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center">
                      <Clock className="h-4 w-4 mr-2" />
                      Execution Timeline
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="text-sm space-y-2">
                    {compExec.started_at && (
                      <div className="flex justify-between">
                        <span className="text-scurry-latte">Started:</span>
                        <span>{new Date(compExec.started_at).toLocaleString()}</span>
                      </div>
                    )}
                    {compExec.completed_at && (
                      <div className="flex justify-between">
                        <span className="text-scurry-latte">Completed:</span>
                        <span>{new Date(compExec.completed_at).toLocaleString()}</span>
                      </div>
                    )}
                    {compExec.execution_time && (
                      <div className="flex justify-between">
                        <span className="text-scurry-latte">Duration:</span>
                        <span className="font-medium">{formatExecutionTime(compExec.execution_time)}</span>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Error Details */}
                {compExec.error_message && (
                  <Card className="border-scurry-red/30">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm flex items-center text-scurry-red">
                        <XCircle className="h-4 w-4 mr-2" />
                        Error Details
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="bg-scurry-red-light p-3 rounded-md">
                        <pre className="text-xs text-scurry-red whitespace-pre-wrap">
                          {compExec.error_message}
                        </pre>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* Input Data */}
              {compExec.input_data && (
                <Card className="mt-4">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center">
                      <ArrowRight className="h-4 w-4 mr-2 text-scurry-orange" />
                      Input Data
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="bg-scurry-orange-light p-3 rounded-md">
                      <pre className="text-xs text-scurry-espresso whitespace-pre-wrap max-h-40 overflow-y-auto">
                        {formatJsonData(compExec.input_data)}
                      </pre>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Output Data */}
              {compExec.output_data && (
                <Card className="mt-4">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm flex items-center">
                      <ArrowRight className="h-4 w-4 mr-2 text-scurry-green rotate-180" />
                      Output Data
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="bg-scurry-green-light p-3 rounded-md">
                      <pre className="text-xs text-scurry-espresso whitespace-pre-wrap max-h-40 overflow-y-auto">
                        {formatJsonData(compExec.output_data)}
                      </pre>
                    </div>
                  </CardContent>
                </Card>
              )}
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>
    )
  }

  if (!isOpen) return null

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-6xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Activity className="h-5 w-5" />
            <span>Execution Details #{executionId}</span>
          </DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <LoadingSpinner size="lg" />
          </div>
        ) : execution ? (
          <div className="space-y-6">
            {/* Execution Overview */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    {getStatusIcon(execution.status)}
                    <div>
                      <div className="text-sm font-medium">Status</div>
                      <div className={`px-2 py-1 text-xs rounded-full ${getStatusColor(execution.status)}`}>
                        {execution.status}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    <Calendar className="h-4 w-4 text-scurry-gray-muted" />
                    <div>
                      <div className="text-sm font-medium">Started</div>
                      <div className="text-sm text-scurry-latte">
                        {formatRelativeTime(new Date(execution.started_at))}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-scurry-gray-muted" />
                    <div>
                      <div className="text-sm font-medium">Duration</div>
                      <div className="text-sm text-scurry-latte">
                        {execution.total_execution_time
                          ? formatExecutionTime(execution.total_execution_time)
                          : 'In progress...'
                        }
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Initial Input Data */}
            {execution.input_data && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center">
                    <Database className="h-5 w-5 mr-2" />
                    Initial Input Data
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-scurry-gray-light p-4 rounded-md">
                    <pre className="text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
                      {formatJsonData(execution.input_data)}
                    </pre>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* RAG Activity — render even when null/empty so users see "RAG not invoked"
                rather than wondering if the run skipped a feature flag. */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center">
                  <Activity className="h-5 w-5 mr-2" />
                  RAG Activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                <RagPanel trace={execution.rag_trace} />
              </CardContent>
            </Card>

            {/* Component Executions */}
            <div>
              <h3 className="text-lg font-semibold mb-4 flex items-center">
                <FileText className="h-5 w-5 mr-2" />
                Component Execution Log
              </h3>
              {execution.component_executions && execution.component_executions.length > 0 ? (
                <div>
                  {/* Sort component executions by their component's order field */}
                  {execution.component_executions
                    .slice()  // Create a copy to avoid mutating the original array
                    .sort((a, b) => {
                      // Find the components for each execution
                      const componentA = workflow?.components.find(c => c.id === a.component_id)
                      const componentB = workflow?.components.find(c => c.id === b.component_id)

                      // Sort by component order (ascending)
                      const orderA = componentA?.order ?? 999
                      const orderB = componentB?.order ?? 999
                      return orderA - orderB
                    })
                    .map((compExec, index) => (
                      <ComponentExecutionDetails
                        key={compExec.id}
                        compExec={compExec}
                        index={index}
                      />
                    ))
                  }
                </div>
              ) : (
                <Card>
                  <CardContent className="p-6 text-center">
                    <FileText className="h-8 w-8 text-scurry-gray-muted mx-auto mb-2" />
                    <p className="text-scurry-latte">No component execution details available</p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Final Results */}
            {execution.results && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center">
                    <CheckCircle className="h-5 w-5 mr-2 text-scurry-green" />
                    Final Results
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-scurry-green-light p-4 rounded-md">
                    <pre className="text-sm whitespace-pre-wrap max-h-60 overflow-y-auto">
                      {formatJsonData(execution.results)}
                    </pre>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Error Message */}
            {execution.error_message && (
              <Card className="border-scurry-red/30">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center text-scurry-red">
                    <XCircle className="h-5 w-5 mr-2" />
                    Execution Error
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="bg-scurry-red-light p-4 rounded-md">
                    <pre className="text-sm text-scurry-red whitespace-pre-wrap">
                      {execution.error_message}
                    </pre>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          <div className="text-center py-8">
            <AlertTriangle className="h-12 w-12 text-scurry-gray-muted mx-auto mb-4" />
            <p className="text-scurry-latte">Execution details not found</p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default ExecutionDetailsModal