import React, { useState, useEffect, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import LoadingSpinner from '@/components/ui/loading-spinner'
import { workflowApi, Workflow } from '@/lib/api'

interface EditUniversalRulesModalProps {
  open: boolean
  onClose: () => void
  workflow: Workflow
}

const EditUniversalRulesModal: React.FC<EditUniversalRulesModalProps> = ({
  open,
  onClose,
  workflow,
}) => {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [value, setValue] = useState('')
  const initializedForOpen = useRef(false)

  // Set form value ONLY when the modal opens — not on every workflow prop change
  useEffect(() => {
    if (open && !initializedForOpen.current) {
      setValue(workflow.universal_rules || '')
      initializedForOpen.current = true
    }
    if (!open) {
      initializedForOpen.current = false
    }
  }, [open, workflow.universal_rules])

  const updateMutation = useMutation({
    mutationFn: (data: { universal_rules: string }) =>
      workflowApi.update(workflow.id, data),
    onSuccess: (response) => {
      queryClient.setQueryData(['workflow', workflow.id], response.data)
      queryClient.invalidateQueries({ queryKey: ['workflows'] })
      onClose()
    },
    onError: (error: any) => {
      setError(error.response?.data?.detail || 'Failed to update universal rules')
    },
  })

  const handleSave = () => {
    setError(null)
    updateMutation.mutate({ universal_rules: value })
  }

  const handleClose = () => {
    setError(null)
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit Universal Rules</DialogTitle>
          <DialogDescription>
            Update the rules that will be applied to all AI prompts in this workflow.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          <div>
            <label htmlFor="universal_rules" className="block text-sm font-medium text-gray-700 mb-1">
              Universal Rules
            </label>
            <Textarea
              id="universal_rules"
              placeholder="e.g., Always be professional and polite. Focus on business value. Keep responses concise."
              value={value}
              onChange={(e) => setValue(e.target.value)}
              rows={5}
              className="resize-none"
            />
            <p className="mt-1 text-xs text-gray-500">
              These rules will be automatically injected into all AI prompts for this workflow
            </p>
          </div>

          <div className="flex justify-end space-x-3 pt-4">
            <Button
              type="button"
              variant="outline"
              onClick={handleClose}
              disabled={updateMutation.isPending}
            >
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={updateMutation.isPending}>
              {updateMutation.isPending ? (
                <div className="flex items-center">
                  <LoadingSpinner size="sm" className="mr-2" />
                  Saving...
                </div>
              ) : (
                'Save Rules'
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default EditUniversalRulesModal
