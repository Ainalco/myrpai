import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowRight,
  Clock,
  Copy,
  Eye,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  User2,
  Workflow,
  Zap,
} from "lucide-react";
import React, { useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";
import CreateWorkflowModal from "@/components/workflows/CreateWorkflowModal";
import DeleteWorkflowModal from "@/components/workflows/DeleteWorkflowModal";
import { useAuth } from "@/contexts/AuthContext";
import { workflowApi, Workflow as WorkflowType } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

const WorkflowsPage: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState("");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowType | null>(
    null
  );
  const [editingWorkflowId, setEditingWorkflowId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [duplicatingWorkflowId, setDuplicatingWorkflowId] = useState<number | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { user } = useAuth();

  const { data: workflows, isLoading } = useQuery({
    queryKey: ["workflows"],
    queryFn: () => workflowApi.getAll().then((res) => res.data),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => workflowApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setDeleteModalOpen(false);
      setSelectedWorkflow(null);
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      workflowApi.update(id, { is_active }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      toast({
        title: "Success",
        description: `Workflow ${variables.is_active ? "activated" : "deactivated"} successfully`,
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to update workflow status",
        variant: "destructive",
      });
    },
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      workflowApi.update(id, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setEditingWorkflowId(null);
      toast({ title: "Success", description: "Workflow renamed successfully" });
    },
    onError: () => {
      setEditingWorkflowId(null);
      toast({ title: "Error", description: "Failed to rename workflow", variant: "destructive" });
    },
  });

  const filteredWorkflows =
    workflows?.filter(
      (workflow) =>
        workflow.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        workflow.description?.toLowerCase().includes(searchTerm.toLowerCase())
    ) || [];

  const handleRenameClick = (workflow: WorkflowType) => {
    setEditingWorkflowId(workflow.id);
    setEditName(workflow.name);
    setTimeout(() => nameInputRef.current?.focus(), 0);
  };

  const handleSaveRename = (workflow: WorkflowType) => {
    if (editName.trim() && editName.trim() !== workflow.name) {
      renameMutation.mutate({ id: workflow.id, name: editName.trim() });
    } else {
      setEditingWorkflowId(null);
    }
  };

  const handleCancelRename = () => {
    setEditingWorkflowId(null);
  };

  const handleNameKeyDown = (e: React.KeyboardEvent, workflow: WorkflowType) => {
    if (e.key === "Enter") {
      handleSaveRename(workflow);
    } else if (e.key === "Escape") {
      handleCancelRename();
    }
  };

  const handleDeleteClick = (workflow: WorkflowType) => {
    setSelectedWorkflow(workflow);
    setDeleteModalOpen(true);
  };

  const handleDeleteConfirm = () => {
    if (selectedWorkflow) {
      deleteMutation.mutate(selectedWorkflow.id);
    }
  };

  const handleDuplicateWorkflow = async (workflow: WorkflowType) => {
    try {
      setDuplicatingWorkflowId(workflow.id);

      const exportResponse = await workflowApi.export(workflow.id);
      const duplicateName = `${workflow.name} (Copy)`;

      const createResponse = await workflowApi.create({
        name: duplicateName,
        description: workflow.description || "",
        universal_rules: workflow.universal_rules || "",
      });

      const newWorkflowId = createResponse.data.id;
      const importData = {
        ...exportResponse.data,
        workflow: {
          ...exportResponse.data.workflow,
          name: duplicateName,
        },
      };

      await workflowApi.import(newWorkflowId, importData);

      await queryClient.invalidateQueries({ queryKey: ["workflows"] });

      toast({
        title: "Success",
        description: `Workflow duplicated successfully as "${duplicateName}".`,
      });
    } catch (error) {
      console.error("Duplicate failed:", error);
      const message =
        error instanceof Error
          ? error.message
          : "Failed to duplicate workflow. Please try again.";
      toast({
        title: "Error",
        description: message,
        variant: "destructive",
      });
    } finally {
      setDuplicatingWorkflowId(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
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
              Workflows
            </h1>
            <p className="text-sm sm:text-base text-scurry-latte mt-2">
              Create and manage your automation workflows
            </p>
          </div>
          <Button
            onClick={() => setCreateModalOpen(true)}
            className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange shadow-md hover:shadow-lg hover:scale-105 transition-all duration-200"
          >
            <Plus className="h-4 w-4 mr-2" />
            Create Workflow
          </Button>
        </div>
      </div>

      {/* Search and Stats */}
      <div className="flex items-center justify-between gap-4 bg-white rounded-xl shadow-md p-4 border-0">
        <div className="relative max-w-md flex-1">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-5 w-5 text-scurry-gray-muted" />
          </div>
          <input
            type="text"
            placeholder="Search workflows..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border border-scurry-gray-border rounded-lg focus:ring-2 focus:ring-scurry-orange focus:border-scurry-orange bg-scurry-foam/30 transition-colors"
          />
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-scurry-orange-light/50">
            <div className="p-1.5 rounded-full bg-scurry-orange-light">
              <Workflow className="h-4 w-4 text-scurry-orange" />
            </div>
            <div>
              <span className="text-lg font-bold text-scurry-espresso">{filteredWorkflows.length}</span>
              <span className="text-xs text-scurry-latte ml-1">total</span>
            </div>
          </div>
          <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-scurry-green-light/50">
            <div className="p-1.5 rounded-full bg-scurry-green-light">
              <Activity className="h-4 w-4 text-scurry-green" />
            </div>
            <div>
              <span className="text-lg font-bold text-scurry-espresso">{filteredWorkflows.filter((w) => w.is_active).length}</span>
              <span className="text-xs text-scurry-latte ml-1">active</span>
            </div>
          </div>
        </div>
      </div>

      {/* Workflows Grid */}
      {filteredWorkflows.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 sm:gap-5">
          {filteredWorkflows.map((workflow) => (
            <div
              key={workflow.id}
              className="bg-white rounded-xl overflow-hidden border-0 shadow-md hover:shadow-lg transition-all duration-200 group"
            >
              {/* Gradient accent bar */}
              <div className={`h-1.5 ${
                workflow.is_active
                  ? 'bg-gradient-to-r from-scurry-orange to-scurry-energy-burst'
                  : 'bg-gradient-to-r from-scurry-gray-muted to-scurry-latte'
              }`} />

              <div className="p-4 sm:p-5">
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-start space-x-3 flex-1">
                    <div className="w-11 h-11 bg-gradient-to-br from-scurry-orange-light to-scurry-foam rounded-xl flex items-center justify-center flex-shrink-0 group-hover:scale-110 transition-transform duration-200">
                      <Zap className="h-5 w-5 text-scurry-orange" />
                    </div>
                    <div className="flex-1 min-w-0">
                      {editingWorkflowId === workflow.id ? (
                        <input
                          ref={nameInputRef}
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => handleNameKeyDown(e, workflow)}
                          onBlur={() => handleSaveRename(workflow)}
                          className="text-lg font-semibold text-scurry-espresso border border-scurry-orange rounded-lg px-2 py-0.5 w-full focus:outline-none focus:ring-2 focus:ring-scurry-orange"
                        />
                      ) : (
                        <div className="flex items-center gap-1.5 group/rename">
                          <h3 className="text-lg font-semibold text-scurry-espresso truncate group-hover:text-scurry-orange transition-colors">
                            {workflow.name}
                          </h3>
                          <button
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              handleRenameClick(workflow);
                            }}
                            className="opacity-0 group-hover/rename:opacity-100 transition-opacity p-1 hover:bg-scurry-foam rounded flex-shrink-0"
                            title="Rename workflow"
                          >
                            <Pencil className="h-3.5 w-3.5 text-scurry-latte" />
                          </button>
                        </div>
                      )}
                      <p className="text-sm text-scurry-gray-muted mt-1 line-clamp-2">
                        {workflow.description || "No description provided"}
                      </p>
                      {workflow.owner_name && (
                        <div className="flex items-center gap-1 mt-1.5">
                          <User2 className="h-3 w-3 text-scurry-latte" />
                          <span className="text-xs text-scurry-latte">
                            {workflow.owner_name === user?.full_name || workflow.owner_name === user?.email
                              ? "You"
                              : workflow.owner_name}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2 ml-2">
                    <div
                      className={`flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-medium ${
                        workflow.is_active
                          ? "bg-scurry-green-light text-scurry-green"
                          : "bg-scurry-gray-light text-scurry-latte"
                      }`}
                    >
                      <div
                        className={`w-1.5 h-1.5 rounded-full ${
                          workflow.is_active ? "bg-scurry-green animate-pulse" : "bg-scurry-gray-muted"
                        }`}
                      />
                      <span>{workflow.is_active ? "Active" : "Inactive"}</span>
                    </div>
                    <Switch
                      checked={workflow.is_active}
                      onCheckedChange={(checked) =>
                        toggleActiveMutation.mutate({
                          id: workflow.id,
                          is_active: checked,
                        })
                      }
                      disabled={toggleActiveMutation.isPending}
                      onClick={(e) => e.stopPropagation()}
                      className="ml-1"
                    />
                  </div>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                  <div className="bg-gradient-to-br from-scurry-foam to-scurry-orange-light/30 rounded-lg p-3 border border-scurry-orange/10">
                    <div className="flex items-center space-x-2">
                      <div className="p-1.5 rounded-full bg-scurry-orange-light">
                        <Settings className="h-3.5 w-3.5 text-scurry-orange" />
                      </div>
                      <div>
                        <p className="text-xs text-scurry-gray-muted">Components</p>
                        <p className="text-sm font-bold text-scurry-espresso">
                          {workflow.components.length}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="bg-gradient-to-br from-scurry-foam to-scurry-blue-bg/30 rounded-lg p-3 border border-scurry-blue-text/10">
                    <div className="flex items-center space-x-2">
                      <div className="p-1.5 rounded-full bg-scurry-blue-bg">
                        <Clock className="h-3.5 w-3.5 text-scurry-blue-text" />
                      </div>
                      <div>
                        <p className="text-xs text-scurry-gray-muted">Updated</p>
                        <p className="text-xs font-medium text-scurry-espresso">
                          {formatRelativeTime(
                            new Date(workflow.updated_at || workflow.created_at)
                          )}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center justify-between pt-4 border-t border-scurry-gray-border/50">
                  <div className="flex space-x-2">
                    <Link to={`/workflows/${workflow.id}`}>
                      <Button variant="outline" size="sm" className="hover:border-scurry-orange hover:text-scurry-orange">
                        <Eye className="h-4 w-4 mr-1" />
                        View
                      </Button>
                    </Link>
                    <Link to={`/workflows/${workflow.id}/processing`}>
                      <Button size="sm" className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover hover:from-scurry-orange-hover hover:to-scurry-orange shadow-sm">
                        <Settings className="h-4 w-4 mr-1" />
                        Configure
                      </Button>
                    </Link>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDuplicateWorkflow(workflow)}
                      disabled={duplicatingWorkflowId === workflow.id}
                      className="hover:border-scurry-orange hover:text-scurry-orange"
                    >
                      <Copy className="h-4 w-4 mr-1" />
                      {duplicatingWorkflowId === workflow.id ? "Copying..." : "Copy"}
                    </Button>
                  </div>
                  <button
                    onClick={() => handleDeleteClick(workflow)}
                    className="p-2 text-scurry-gray-muted hover:text-scurry-red hover:bg-scurry-red-light rounded-lg transition-colors"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-16 bg-white rounded-xl shadow-md border-0">
          <div className="max-w-md mx-auto">
            {searchTerm ? (
              <div className="space-y-4">
                <div className="p-4 rounded-full bg-scurry-gray-light inline-block mb-2">
                  <Search className="h-10 w-10 text-scurry-gray-muted" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-scurry-espresso mb-2">
                    No workflows found
                  </h3>
                  <p className="text-scurry-latte mb-4">
                    No workflows match "{searchTerm}". Try adjusting your search terms.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setSearchTerm("")}
                    className="hover:border-scurry-orange hover:text-scurry-orange"
                  >
                    Clear Search
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="p-4 rounded-full bg-scurry-orange-light inline-block mb-2">
                  <Workflow className="h-10 w-10 text-scurry-orange" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-scurry-espresso mb-2">
                    No workflows yet
                  </h3>
                  <p className="text-scurry-latte mb-4">
                    Create your first workflow to transform call transcripts into actionable insights.
                  </p>
                  <Button
                    onClick={() => setCreateModalOpen(true)}
                    className="bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white hover:from-scurry-orange-hover hover:to-scurry-orange shadow-md hover:shadow-lg hover:scale-105 transition-all duration-200"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Create Your First Workflow
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      <CreateWorkflowModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
      />

      <DeleteWorkflowModal
        open={deleteModalOpen}
        onClose={() => {
          setDeleteModalOpen(false);
          setSelectedWorkflow(null);
        }}
        workflow={selectedWorkflow}
        onConfirm={handleDeleteConfirm}
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
};

export default WorkflowsPage;
