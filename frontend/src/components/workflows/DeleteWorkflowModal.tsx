import React from 'react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { useAuth } from '@/contexts/AuthContext'
import { Workflow } from '@/lib/api'

interface DeleteWorkflowModalProps {
  open: boolean
  onClose: () => void
  workflow: Workflow | null
  onConfirm: () => void
  isLoading: boolean
}

const DeleteWorkflowModal: React.FC<DeleteWorkflowModalProps> = ({
  open,
  onClose,
  workflow,
  onConfirm,
  isLoading,
}) => {
  const { user } = useAuth()
  const isOwnWorkflow = !workflow?.owner_name ||
    workflow.owner_name === user?.full_name ||
    workflow.owner_name === user?.email
  if (!workflow) return null

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Delete Workflow</DialogTitle>
          <DialogDescription>
            Are you sure you want to delete this workflow? This action cannot be undone.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <div className="bg-gray-50 rounded-lg p-4">
            <h4 className="font-medium text-gray-900">{workflow.name}</h4>
            {workflow.description && (
              <p className="text-sm text-gray-600 mt-1">{workflow.description}</p>
            )}
            <div className="flex items-center mt-2 text-xs text-gray-500">
              <span>{workflow.components.length} components</span>
              <span className="mx-2">•</span>
              <span>{workflow.is_active ? 'Active' : 'Inactive'}</span>
              {workflow.owner_name && (
                <>
                  <span className="mx-2">•</span>
                  <span>Created by {isOwnWorkflow ? 'you' : workflow.owner_name}</span>
                </>
              )}
            </div>
          </div>
        </div>

        {!isOwnWorkflow && workflow.owner_name && (
          <div className="bg-red-50 border border-red-200 rounded-md p-3">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg
                  className="h-5 w-5 text-red-400"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">This workflow belongs to {workflow.owner_name}</h3>
                <div className="mt-1 text-sm text-red-700">
                  <p>You are about to delete a workflow created by another team member. They will lose access to this workflow.</p>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-yellow-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-yellow-800">Warning</h3>
              <div className="mt-1 text-sm text-yellow-700">
                <p>
                  This will permanently delete the workflow and all its components, 
                  connections, and execution history. This action cannot be undone.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end space-x-3 pt-4">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? (
              <div className="flex items-center">
                <LoadingSpinner size="sm" className="mr-2" />
                Deleting...
              </div>
            ) : (
              'Delete Workflow'
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default DeleteWorkflowModal