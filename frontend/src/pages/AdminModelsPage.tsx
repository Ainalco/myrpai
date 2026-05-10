import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, Power } from 'lucide-react'
import { adminApi, AiModel } from '@/lib/api'

interface DialogState {
  open: boolean
  editing: AiModel | null
}

export default function AdminModelsPage() {
  const queryClient = useQueryClient()
  const [dialog, setDialog] = useState<DialogState>({ open: false, editing: null })
  const [formData, setFormData] = useState({
    display_name: '',
    model_id: '',
    input_cost_per_million: 0,
    output_cost_per_million: 0,
  })

  const { data: models, isLoading } = useQuery({
    queryKey: ['admin', 'models'],
    queryFn: () => adminApi.getModels().then((r) => r.data),
  })

  const createMutation = useMutation({
    mutationFn: adminApi.createModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'models'] })
      setDialog({ open: false, editing: null })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<{ display_name: string; input_cost_per_million: number; output_cost_per_million: number }> }) =>
      adminApi.updateModel(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'models'] })
      setDialog({ open: false, editing: null })
    },
  })

  const activateMutation = useMutation({
    mutationFn: adminApi.activateModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'models'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: adminApi.deleteModel,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'models'] })
    },
  })

  const openAddDialog = () => {
    setFormData({ display_name: '', model_id: '', input_cost_per_million: 0, output_cost_per_million: 0 })
    setDialog({ open: true, editing: null })
  }

  const openEditDialog = (model: AiModel) => {
    setFormData({
      display_name: model.display_name,
      model_id: model.model_id,
      input_cost_per_million: model.input_cost_per_million,
      output_cost_per_million: model.output_cost_per_million,
    })
    setDialog({ open: true, editing: model })
  }

  const handleSave = () => {
    if (dialog.editing) {
      updateMutation.mutate({
        id: dialog.editing.id,
        data: {
          display_name: formData.display_name,
          input_cost_per_million: formData.input_cost_per_million,
          output_cost_per_million: formData.output_cost_per_million,
        },
      })
    } else {
      createMutation.mutate(formData)
    }
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header with Light Gradient */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-8 -mt-8 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        {/* Decorative accent */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />

        <div className="flex items-center justify-between relative z-10">
          <div>
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">
              Admin Portal
            </h1>
            <p className="text-sm sm:text-base text-scurry-latte mt-2">
              Manage AI models and pricing
            </p>
          </div>
        </div>
      </div>

      {/* Sub-nav */}
      <div className="border-b border-scurry-gray-border">
        <nav className="flex gap-4">
          <Link
            to="/admin"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
          >
            Overview
          </Link>
          <Link
            to="/admin/usage"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-transparent text-scurry-latte hover:text-scurry-espresso"
          >
            Usage &amp; Cost
          </Link>
          <Link
            to="/admin/models"
            className="pb-3 px-1 text-sm font-medium border-b-2 transition-colors border-scurry-orange text-scurry-orange"
          >
            Models
          </Link>
        </nav>
      </div>

      {/* Add Model button */}
      <div className="flex justify-end">
        <button
          onClick={openAddDialog}
          className="bg-scurry-orange text-white hover:bg-scurry-orange/90 px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2"
        >
          <Plus className="h-4 w-4" />
          Add Model
        </button>
      </div>

      {/* Models table */}
      {isLoading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-scurry-orange" />
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-scurry-gray-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-scurry-foam text-left text-xs text-scurry-latte uppercase tracking-wider">
                  <th className="px-4 py-3">Display Name</th>
                  <th className="px-4 py-3">Model ID</th>
                  <th className="px-4 py-3">Input $/M</th>
                  <th className="px-4 py-3">Output $/M</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-scurry-gray-border">
                {models && models.length > 0 ? (
                  models.map((model) => (
                    <tr key={model.id} className="hover:bg-scurry-foam/50">
                      <td className="px-4 py-3 font-medium text-scurry-espresso">{model.display_name}</td>
                      <td className="px-4 py-3 text-scurry-latte font-mono text-xs">{model.model_id}</td>
                      <td className="px-4 py-3 text-scurry-espresso">${model.input_cost_per_million.toFixed(2)}</td>
                      <td className="px-4 py-3 text-scurry-espresso">${model.output_cost_per_million.toFixed(2)}</td>
                      <td className="px-4 py-3">
                        {model.is_active ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
                            Inactive
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openEditDialog(model)}
                            className="text-scurry-latte hover:text-scurry-espresso p-1 rounded"
                            title="Edit"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          {!model.is_active && (
                            <>
                              <button
                                onClick={() => activateMutation.mutate(model.id)}
                                className="text-scurry-latte hover:text-green-600 p-1 rounded"
                                title="Set Active"
                              >
                                <Power className="h-4 w-4" />
                              </button>
                              <button
                                onClick={() => deleteMutation.mutate(model.id)}
                                className="text-red-400 hover:text-red-600 p-1 rounded"
                                title="Delete"
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-scurry-gray-muted">
                      No models found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Add/Edit Dialog */}
      {dialog.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setDialog({ open: false, editing: null })}
          />
          <div className="relative bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-scurry-espresso mb-4">
              {dialog.editing ? 'Edit Model' : 'Add Model'}
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-scurry-espresso mb-1">
                  Display Name
                </label>
                <input
                  type="text"
                  value={formData.display_name}
                  onChange={(e) => setFormData({ ...formData, display_name: e.target.value })}
                  className="w-full border border-scurry-gray-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-scurry-orange/50 focus:border-scurry-orange"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-scurry-espresso mb-1">
                  Model ID
                </label>
                <input
                  type="text"
                  value={formData.model_id}
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value })}
                  disabled={!!dialog.editing}
                  className="w-full border border-scurry-gray-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-scurry-orange/50 focus:border-scurry-orange disabled:bg-gray-50 disabled:text-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-scurry-espresso mb-1">
                  Input Cost per Million
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.input_cost_per_million}
                  onChange={(e) => setFormData({ ...formData, input_cost_per_million: parseFloat(e.target.value) || 0 })}
                  className="w-full border border-scurry-gray-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-scurry-orange/50 focus:border-scurry-orange"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-scurry-espresso mb-1">
                  Output Cost per Million
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.output_cost_per_million}
                  onChange={(e) => setFormData({ ...formData, output_cost_per_million: parseFloat(e.target.value) || 0 })}
                  className="w-full border border-scurry-gray-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-scurry-orange/50 focus:border-scurry-orange"
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setDialog({ open: false, editing: null })}
                className="px-4 py-2 text-sm font-medium text-scurry-latte hover:text-scurry-espresso rounded-lg border border-scurry-gray-border"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={createMutation.isPending || updateMutation.isPending}
                className="bg-scurry-orange text-white hover:bg-scurry-orange/90 px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
              >
                {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
