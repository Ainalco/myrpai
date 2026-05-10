import React, { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { workflowApi } from '@/lib/api'

interface CreateWorkflowModalProps {
  open: boolean
  onClose: () => void
}

interface CreateWorkflowForm {
  name: string
  description: string
}

const CreateWorkflowModal: React.FC<CreateWorkflowModalProps> = ({
  open,
  onClose,
}) => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateWorkflowForm>()

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description?: string }) =>
      workflowApi.create(data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      queryClient.invalidateQueries({ queryKey: ['workflow-stats'] })
      reset()
      onClose()
      // Navigate to the new workflow's processing dashboard
      navigate(`/workflows/${response.data.id}/processing`)
    },
    onError: (error: any) => {
      setError(error.response?.data?.detail || 'Failed to create workflow')
    },
  })

  const onSubmit = (data: CreateWorkflowForm) => {
    setError(null)
    createMutation.mutate({
      name: data.name,
      description: data.description || undefined,
    })
  }

  const handleClose = () => {
    reset()
    setError(null)
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Create New Workflow</DialogTitle>
          <DialogDescription>
            Create a new automation workflow for call transcript processing and CRM integration.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <div>
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-1">
              Workflow Name *
            </label>
            <Input
              id="name"
              placeholder="e.g., Call Summary & Follow-up"
              {...register('name', { required: 'Workflow name is required' })}
              className={errors.name ? 'border-red-300' : ''}
            />
            {errors.name && (
              <p className="mt-1 text-sm text-red-600">{errors.name.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <Input
              id="description"
              placeholder="Brief description of what this workflow does"
              {...register('description')}
            />
            <p className="mt-1 text-xs text-gray-500">
              Optional - helps you identify the workflow's purpose
            </p>
          </div>

          <div className="flex justify-end space-x-3 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? (
                <div className="flex items-center">
                  <LoadingSpinner size="sm" className="mr-2" />
                  Creating...
                </div>
              ) : (
                'Create Workflow'
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default CreateWorkflowModal