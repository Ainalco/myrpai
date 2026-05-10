import React, { useState, useRef, useEffect } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { AxiosError } from 'axios'
import {
  Settings,
  Upload,
  Download,
  Copy,
  Save,
  FileText,
  ArrowLeft
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import LoadingSpinner from '@/components/ui/loading-spinner'
import PipelineSidebar from '@/components/processing/PipelineSidebar'
import ComponentConfigPanel from '@/components/processing/ComponentConfigPanel'
import TestResultsModal from '@/components/processing/TestResultsModal'
import EditUniversalRulesModal from '@/components/workflows/EditUniversalRulesModal'
import { workflowApi, componentApi } from '@/lib/api'
import { useToast } from '@/components/ui/use-toast'
import { componentTestKeys } from '@/hooks/useComponentTestResults'

const ProcessingDashboard: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const workflowId = parseInt(id!, 10)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { toast } = useToast()

  const [selectedComponentId, setSelectedComponentId] = useState<number | null>(null)
  const [testResultsOpen, setTestResultsOpen] = useState(false)
  const [isUniversalRulesModalOpen, setIsUniversalRulesModalOpen] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [isDuplicating, setIsDuplicating] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDragging, setIsDragging] = useState(false)

  const { data: workflow, isLoading: workflowLoading } = useQuery({
    queryKey: ['workflow', workflowId],
    queryFn: () => workflowApi.getById(workflowId).then(res => res.data),
    enabled: !!workflowId,
  })

  const { data: components, isLoading: componentsLoading } = useQuery({
    queryKey: ['components', workflowId],
    queryFn: () => componentApi.getByWorkflow(workflowId).then(res => res.data),
    enabled: !!workflowId,
  })

  const { data: connections } = useQuery({
    queryKey: ['connections', workflowId],
    queryFn: () => componentApi.getConnections(workflowId).then(res => res.data),
    enabled: !!workflowId,
  })

  // Listen for configuration save completion - MUST be before any early returns
  useEffect(() => {
    const handleSaveComplete = (event: Event) => {
      const customEvent = event as CustomEvent
      setIsSaving(false)

      if (customEvent.detail?.success) {
        toast({
          title: "Success",
          description: "Configuration saved successfully!",
        })
      } else {
        toast({
          title: "Error",
          description: customEvent.detail?.error || "Failed to save configuration. Please try again.",
          variant: "destructive",
        })
      }
    }

    window.addEventListener('configuration-saved', handleSaveComplete)
    return () => {
      window.removeEventListener('configuration-saved', handleSaveComplete)
    }
  }, [toast])

  // Clear test results when workflow changes
  useEffect(() => {
    return () => {
      queryClient.removeQueries({
        queryKey: componentTestKeys.workflow(workflowId),
      })
    }
  }, [workflowId, queryClient])

  if (workflowLoading || componentsLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!workflow) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-display font-bold text-scurry-espresso mb-2">
            Workflow Not Found
          </h1>
          <p className="text-scurry-latte mb-4">
            The workflow you're looking for doesn't exist.
          </p>
        </div>
      </div>
    )
  }

  const selectedComponent = selectedComponentId
    ? components?.find(c => c.id === selectedComponentId)
    : components?.[0] // Default to first component

  const handleOpenUniversalRulesModal = () => {
    setIsUniversalRulesModalOpen(true)
  }

  const handleCloseUniversalRulesModal = () => {
    setIsUniversalRulesModalOpen(false)
  }

  const handleExport = async () => {
    try {
      setIsExporting(true)
      const response = await workflowApi.export(workflowId)

      // Create a blob and download the file
      const blob = new Blob([JSON.stringify(response.data, null, 2)], {
        type: 'application/json',
      })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `workflow-${workflowId}-${workflow?.name || 'export'}.json`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)

      toast({
        title: "Success",
        description: "Workflow configuration exported successfully!",
      })
    } catch (error) {
      console.error('Export failed:', error)
      const axiosError = error as AxiosError<{ detail?: string }>
      const errorDetail =
        axiosError.response?.data?.detail ||
        axiosError.message ||
        'Failed to export workflow configuration. Please try again.'
      toast({
        title: "Error",
        description: errorDetail,
        variant: "destructive",
      })
    } finally {
      setIsExporting(false)
    }
  }

  const handleImport = () => {
    fileInputRef.current?.click()
  }

  const handleDuplicate = async () => {
    if (!workflow) return

    try {
      setIsDuplicating(true)

      const exportResponse = await workflowApi.export(workflowId)
      const duplicateName = `${workflow.name} (Copy)`

      const createResponse = await workflowApi.create({
        name: duplicateName,
        description: workflow.description || '',
        universal_rules: workflow.universal_rules || '',
      })

      const newWorkflowId = createResponse.data.id
      const importData = {
        ...exportResponse.data,
        workflow: {
          ...exportResponse.data.workflow,
          name: duplicateName,
        },
      }

      await workflowApi.import(newWorkflowId, importData)

      await queryClient.invalidateQueries({ queryKey: ['workflows'] })

      toast({
        title: "Success",
        description: `Workflow duplicated successfully as "${duplicateName}".`,
      })

      navigate(`/workflows/${newWorkflowId}/processing`)
    } catch (error) {
      console.error('Duplicate failed:', error)
      const axiosError = error as AxiosError<{ detail?: string }>
      const errorDetail =
        axiosError.response?.data?.detail ||
        axiosError.message ||
        'Failed to duplicate workflow. Please try again.'
      toast({
        title: "Error",
        description: errorDetail,
        variant: "destructive",
      })
    } finally {
      setIsDuplicating(false)
    }
  }

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    try {
      setIsImporting(true)
      const fileContent = await file.text()
      const importData = JSON.parse(fileContent)

      // Validate the import data structure
      if (!importData.workflow || !importData.components || !importData.connections) {
        throw new Error('Invalid workflow configuration file')
      }

      await workflowApi.import(workflowId, importData)

      // Refresh all queries
      await queryClient.invalidateQueries({ queryKey: ['workflow', workflowId] })
      await queryClient.invalidateQueries({ queryKey: ['components', workflowId] })
      await queryClient.invalidateQueries({ queryKey: ['connections', workflowId] })

      toast({
        title: "Success",
        description: "Workflow configuration imported successfully!",
      })

      // Reset selected component
      setSelectedComponentId(null)
    } catch (error) {
      console.error('Import failed:', error)
      toast({
        title: "Error",
        description: "Failed to import workflow configuration. Please ensure the file is valid.",
        variant: "destructive",
      })
    } finally {
      setIsImporting(false)
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleSaveConfiguration = () => {
    // Trigger the save button in the currently displayed component
    setIsSaving(true)
    const event = new CustomEvent('save-configuration', {
      detail: { componentId: selectedComponentId || components?.[0]?.id }
    })
    window.dispatchEvent(event)
  }

  return (
    <div className="min-h-screen bg-scurry-gray-light">
      {/* Header */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />
        <div className="px-4 sm:px-6 lg:px-8 py-4 sm:py-6 relative z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3 sm:space-x-4">
              <Link to={`/workflows/${workflowId}`}>
                <Button variant="ghost" size="sm" className="text-scurry-latte hover:bg-scurry-foam rounded-lg">
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back
                </Button>
              </Link>
              <div>
                <h1 className="text-xl sm:text-2xl lg:text-3xl font-display font-bold text-scurry-espresso">
                  {workflow.name}
                </h1>
                <p className="text-sm sm:text-base text-scurry-latte mt-1">
                  {workflow.description} • Powered by caffeine & acorns
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-1 sm:space-x-2">
              <Button
                variant="outline"
                onClick={handleOpenUniversalRulesModal}
                size="sm"
                className="flex items-center border-scurry-latte/25 text-scurry-espresso font-medium rounded-lg"
              >
                <Settings className="h-4 w-4" />
                <span className="hidden md:inline ml-2">Universal Rules</span>
              </Button>
              <Button
                variant="outline"
                onClick={handleImport}
                disabled={isImporting}
                size="sm"
                className="flex items-center border-scurry-latte/25 text-scurry-espresso font-medium rounded-lg"
              >
                <Upload className="h-4 w-4" />
                <span className="hidden md:inline ml-2">{isImporting ? 'Importing...' : 'Import'}</span>
              </Button>
              <Button
                variant="outline"
                onClick={handleExport}
                disabled={isExporting}
                size="sm"
                className="flex items-center border-scurry-latte/25 text-scurry-espresso font-medium rounded-lg"
              >
                <Download className="h-4 w-4" />
                <span className="hidden md:inline ml-2">{isExporting ? 'Exporting...' : 'Export'}</span>
              </Button>
              <Button
                variant="outline"
                onClick={handleDuplicate}
                disabled={isDuplicating}
                size="sm"
                className="flex items-center border-scurry-latte/25 text-scurry-espresso font-medium rounded-lg"
              >
                <Copy className="h-4 w-4" />
                <span className="hidden md:inline ml-2">{isDuplicating ? 'Copying...' : 'Copy'}</span>
              </Button>
              <Button
                onClick={handleSaveConfiguration}
                disabled={isSaving}
                size="sm"
                className="flex items-center bg-gradient-to-br from-scurry-orange to-scurry-orange-hover hover:from-scurry-orange-hover hover:to-scurry-orange-hover text-white font-semibold rounded-lg shadow-lg shadow-scurry-orange/30"
              >
                <Save className="h-4 w-4" />
                <span className="hidden sm:inline ml-2">{isSaving ? 'Saving...' : 'Save'}</span>
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex h-[calc(100vh-90px)] sm:h-[calc(100vh-100px)]">
        {/* Pipeline Sidebar */}
        <div className="w-64 flex-shrink-0 border-r border-scurry-gray-border bg-white overflow-auto">
          <PipelineSidebar
            workflowId={workflowId}
            components={components || []}
            connections={connections || []}
            selectedComponentId={selectedComponentId}
            onComponentSelect={setSelectedComponentId}
            onTestFullProcess={() => setTestResultsOpen(true)}
            onDragStateChange={setIsDragging}
          />
        </div>

        {/* Component Configuration Panel */}
        <div className="flex-1 overflow-auto bg-scurry-gray-light relative">
          {/* Drag overlay */}
          {isDragging && (
            <div className="absolute inset-0 bg-scurry-espresso/50 z-10 pointer-events-none" />
          )}

          {selectedComponent ? (
            <ComponentConfigPanel
              workflowId={workflowId}
              component={selectedComponent}
            />
          ) : (
            <div className="h-full flex items-center justify-center">
              <div className="text-center max-w-md mx-auto p-6 sm:p-8">
                <h3 className="text-xl sm:text-2xl font-display font-bold text-scurry-espresso mb-3">
                  No component selected
                </h3>
                <p className="text-scurry-latte text-base sm:text-lg">
                  Select a component from the sidebar to configure it
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Test Results Modal */}
      <TestResultsModal
        open={testResultsOpen}
        onClose={() => setTestResultsOpen(false)}
        workflowId={workflowId}
      />

      {/* Universal Rules Modal */}
      {workflow && (
        <EditUniversalRulesModal
          open={isUniversalRulesModalOpen}
          onClose={handleCloseUniversalRulesModal}
          workflow={workflow}
        />
      )}

      {/* Hidden file input for import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />
    </div>
  )
}

export default ProcessingDashboard
