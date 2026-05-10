/**
 * ResourcesPage.tsx
 * =================
 * LOCATION: frontend/src/pages/ResourcesPage.tsx
 *
 * Account-level resource library for links and PDFs.
 * Users store resources with labels and descriptions (AI context).
 * Per-email usage mode is configured separately in EmailConfig.tsx Advanced Settings.
 *
 * REQUIRES:
 * - resourceApi in api.ts (included in this update)
 * - Route in App.tsx: <Route path="/resources" element={<ResourcesPage />} />
 * - Sidebar nav in Layout.tsx (Package icon from lucide-react)
 * - Backend: /api/resources endpoints + resources DB table
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Edit3,
  FileText,
  Link2,
  Loader2,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import React, { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/use-toast";
import { resourceApi } from "@/lib/resourceApi";
import type { Resource } from "@/lib/resourceApi";
import { useAuth } from "@/contexts/AuthContext";

// ─── Preset Labels ───
const LINK_PRESETS = [
  { id: "book-call", label: "Book a Call", desc: "Calendly or scheduling link for booking discovery calls and product demos with qualified prospects" },
  { id: "schedule-demo", label: "Schedule a Demo", desc: "Link for prospects who want to see the product in action or asked for a live demonstration" },
  { id: "book-meeting", label: "Book a Meeting", desc: "General meeting scheduling link for when a conversation ends with agreement to meet again" },
  { id: "pick-time", label: "Pick a Time", desc: "Flexible scheduling link for when prospect showed willingness to continue but no time was agreed" },
  { id: "get-started", label: "Get Started", desc: "Onboarding or signup page for prospects who expressed readiness to proceed" },
  { id: "learn-more", label: "Learn More", desc: "Feature page or documentation for prospects asking about capabilities not covered in the meeting" },
  { id: "see-pricing", label: "See Pricing", desc: "Pricing page for when budget or pricing was discussed in the meeting" },
  { id: "view-proposal", label: "View Proposal", desc: "Proposal document link for when prospect requested a formal agreement to review" },
  { id: "download-guide", label: "Download Guide", desc: "Educational content or reference material the prospect can share with their internal team" },
  { id: "read-case-study", label: "Read Case Study", desc: "Customer success story or proof points for when prospect asked for examples of similar customers" },
  { id: "connect-linkedin", label: "Connect on LinkedIn", desc: "LinkedIn profile for relationship-building contexts where a personal connection is appropriate" },
  { id: "visit-website", label: "Visit Our Website", desc: "Company website for when prospect needs general info or wants to explore independently" },
  { id: "custom", label: "✏️ Custom Label", desc: "" },
];

// Plan limits by tier
const PLAN_LIMITS: Record<string, { links: number; files: number; fileSize: number }> = {
  seedling: { links: 2, files: 0, fileSize: 0 },
  oak: { links: 10, files: 5, fileSize: 10 * 1024 * 1024 },
  redwood: { links: 25, files: 15, fileSize: 10 * 1024 * 1024 },
  ancient_forest: { links: 999, files: 999, fileSize: 25 * 1024 * 1024 },
};

const wordCount = (text: string) =>
  text.trim() ? text.trim().split(/\s+/).length : 0;

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

// ─── Add/Edit Resource Modal ───
interface ResourceModalProps {
  open: boolean;
  onClose: () => void;
  type: "link" | "file";
  editResource?: Resource | null;
}

const ResourceModal: React.FC<ResourceModalProps> = ({
  open,
  onClose,
  type,
  editResource,
}) => {
  const isLink = type === "link";
  const isEdit = !!editResource;
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [step, setStep] = useState(isEdit ? 2 : isLink ? 1 : 2);
  const [label, setLabel] = useState(editResource?.label || "");
  const [isCustomLabel, setIsCustomLabel] = useState(!!editResource);
  const [url, setUrl] = useState(editResource?.url || "");
  const [description, setDescription] = useState(editResource?.description || "");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [existingFilename, setExistingFilename] = useState(
    editResource?.file_original_name || "",
  );

  // Reset state when modal opens/closes
  React.useEffect(() => {
    if (open) {
      setStep(editResource ? 2 : isLink ? 1 : 2);
      setLabel(editResource?.label || "");
      setIsCustomLabel(!!editResource);
      setUrl(editResource?.url || "");
      setDescription(editResource?.description || "");
      setSelectedFile(null);
      setExistingFilename(editResource?.file_original_name || "");
    }
  }, [open, editResource, isLink]);

  const createMutation = useMutation({
    mutationFn: async () => {
      if (isLink) {
        return resourceApi.create({ type: "link", label, description, url });
      } else {
        const formData = new FormData();
        if (selectedFile) formData.append("file", selectedFile);
        formData.append("label", label);
        formData.append("description", description || "");
        return resourceApi.upload(formData);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      toast({ title: "Success", description: `${isLink ? "Link" : "PDF"} resource added` });
      onClose();
    },
    onError: (err: any) => {
      toast({
        title: "Error",
        description: err?.response?.data?.detail || "Failed to save resource",
        variant: "destructive",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      resourceApi.update(editResource!.id, { label, description, url } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      toast({ title: "Success", description: "Resource updated" });
      onClose();
    },
    onError: (err: any) => {
      toast({
        title: "Error",
        description: err?.response?.data?.detail || "Failed to update",
        variant: "destructive",
      });
    },
  });

  const handleSave = () => {
    if (isEdit) updateMutation.mutate();
    else createMutation.mutate();
  };

  const pickPreset = (preset: (typeof LINK_PRESETS)[number]) => {
    setLabel(preset.id === "custom" ? "" : preset.label);
    setIsCustomLabel(preset.id === "custom");
    setDescription(preset.desc);
    setStep(2);
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const canSave = label.trim() && (isLink ? url.trim() : selectedFile || existingFilename);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-scurry-orange-light flex items-center justify-center text-sm">
              {isLink ? "🔗" : "📎"}
            </div>
            <div>
              <DialogTitle className="text-scurry-espresso">
                {isEdit ? "Edit" : "Add"} {isLink ? "Link" : "PDF"}
              </DialogTitle>
              <DialogDescription>
                {step === 1 ? "Choose a preset" : "Configure your resource"}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Step 1: Preset picker (links only) */}
        {step === 1 && (
          <div>
            <p className="text-sm font-semibold text-scurry-espresso mb-1">
              Choose a label preset
            </p>
            <p className="text-xs text-scurry-latte mb-4">
              Pre-fills label & description. Fully editable afterward.
            </p>
            <div className="grid grid-cols-2 gap-2 max-h-[50vh] overflow-y-auto">
              {LINK_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => pickPreset(preset)}
                  className="text-left p-3 rounded-xl border border-scurry-gray-border text-sm font-medium text-scurry-espresso hover:border-scurry-orange hover:bg-scurry-orange-light/50 hover:text-scurry-orange transition-all"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Configure — label, URL/upload, description only */}
        {step === 2 && (
          <div className="space-y-5">
            {/* Label */}
            <div>
              <Label className="text-xs font-semibold text-scurry-latte">Label</Label>
              {!isCustomLabel ? (
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="px-3 py-1.5 bg-scurry-orange-light rounded-lg text-sm font-semibold text-scurry-orange border border-scurry-orange/20">
                    {label}
                  </span>
                  <button
                    type="button"
                    onClick={() => setIsCustomLabel(true)}
                    className="text-xs text-scurry-latte hover:text-scurry-orange flex items-center gap-1"
                  >
                    <Edit3 className="h-3 w-3" /> Edit
                  </button>
                </div>
              ) : (
                <div className="mt-1.5">
                  <Input
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    maxLength={30}
                    placeholder="e.g. Grab 15 Minutes"
                  />
                  <p className="text-[11px] text-scurry-gray-muted mt-1">{label.length}/30 characters</p>
                </div>
              )}
            </div>

            {/* URL or Upload */}
            {isLink ? (
              <div>
                <Label className="text-xs font-semibold text-scurry-latte">URL</Label>
                <Input
                  className="mt-1.5"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://calendly.com/your-link"
                  type="url"
                />
              </div>
            ) : (
              <div>
                <Label className="text-xs font-semibold text-scurry-latte">PDF File</Label>
                {!selectedFile && !existingFilename ? (
                  <label className="mt-1.5 flex flex-col items-center gap-2 p-8 border-2 border-dashed border-scurry-gray-border rounded-xl cursor-pointer hover:border-scurry-orange/40 hover:bg-scurry-orange-light/20 transition-colors">
                    <Upload className="h-5 w-5 text-scurry-gray-muted" />
                    <span className="text-sm font-medium text-scurry-espresso">Click to upload</span>
                    <span className="text-xs text-scurry-gray-muted">PDF only · Max 10MB</span>
                    <span className="text-xs text-scurry-gray-muted/70 italic mt-1">For best results, upload focused resources rather than broad documents.</span>
                    <input
                      type="file"
                      accept=".pdf"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setSelectedFile(file);
                          if (!label) setLabel(file.name.replace(".pdf", ""));
                        }
                      }}
                    />
                  </label>
                ) : (
                  <div className="mt-1.5 flex items-center gap-3 p-3 bg-scurry-green-light rounded-xl border border-scurry-green/20">
                    <FileText className="h-4 w-4 text-scurry-green" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-scurry-espresso truncate">
                        {selectedFile?.name || existingFilename}
                      </p>
                      <p className="text-xs text-scurry-green">
                        {selectedFile ? formatFileSize(selectedFile.size) : "Uploaded"} ✓
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => { setSelectedFile(null); setExistingFilename(""); }}
                      className="text-xs text-scurry-red font-semibold hover:underline"
                    >
                      Remove
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Description — AI context */}
            <div>
              <Label className="text-xs font-semibold text-scurry-latte">
                Description <span className="font-normal text-scurry-gray-muted">(max 50 words)</span>
              </Label>
              <p className="text-[11px] text-scurry-gray-muted mb-1.5">
                Tells the AI what this resource is and when it's contextually relevant.
              </p>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder="e.g. Calendly scheduling link for product demos with qualified prospects who expressed interest in seeing the platform"
                className="w-full px-3 py-2 border border-scurry-gray-border rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-scurry-orange/20 focus:border-scurry-orange"
              />
              <p className={`text-[11px] mt-1 ${wordCount(description) > 50 ? "text-scurry-red font-semibold" : "text-scurry-gray-muted"}`}>
                {wordCount(description)}/50 words
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              {!isEdit && isLink && (
                <Button variant="outline" onClick={() => setStep(1)} className="border-scurry-gray-border text-scurry-latte">
                  Back
                </Button>
              )}
              <Button
                onClick={handleSave}
                disabled={isSaving || !canSave}
                className="flex-1 bg-scurry-orange text-white hover:bg-scurry-orange-hover"
              >
                {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isEdit ? "Update" : "Save"} Resource
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

// ─── Resource Row ───
interface ResourceRowProps {
  resource: Resource;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

const ResourceRow: React.FC<ResourceRowProps> = ({ resource, onToggle, onEdit, onDelete }) => (
  <div
    className={`flex items-start gap-4 p-4 rounded-xl border transition-all ${
      resource.is_active
        ? "border-scurry-gray-border bg-white hover:border-scurry-orange/30 hover:shadow-sm"
        : "border-gray-100 bg-scurry-gray-light opacity-50"
    }`}
  >
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <span className="text-sm font-bold text-scurry-espresso">{resource.label}</span>
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-semibold ${
          resource.type === "link"
            ? "bg-scurry-orange-light text-scurry-orange"
            : "bg-scurry-green-light text-scurry-green"
        }`}>
          {resource.type === "link" ? "🔗 Link" : "📎 PDF"}
        </span>
        {!resource.is_active && (
          <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-gray-100 text-scurry-gray-muted">Paused</span>
        )}
      </div>
      {resource.type === "link" && resource.url && (
        <p className="text-xs text-scurry-latte mb-1 truncate">{resource.url}</p>
      )}
      {resource.type === "file" && resource.file_original_name && (
        <p className="text-xs text-scurry-latte mb-1">
          {resource.file_original_name}
          {resource.file_size_bytes && (
            <span className="text-scurry-gray-muted"> · {formatFileSize(resource.file_size_bytes)}</span>
          )}
        </p>
      )}
      {resource.description && (
        <p className="text-[11px] text-scurry-gray-muted leading-relaxed mt-1">{resource.description}</p>
      )}
    </div>
    <div className="flex items-center gap-1.5 flex-shrink-0 pt-0.5">
      <Switch checked={resource.is_active} onCheckedChange={onToggle} />
      <button type="button" onClick={onEdit} className="p-1.5 rounded-lg hover:bg-scurry-orange-light text-scurry-latte hover:text-scurry-orange transition-colors">
        <Edit3 className="h-3.5 w-3.5" />
      </button>
      <button type="button" onClick={onDelete} className="p-1.5 rounded-lg hover:bg-scurry-red-light text-scurry-latte hover:text-scurry-red transition-colors">
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  </div>
);

// ─── Main Page ───
const ResourcesPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"links" | "files">("links");
  const [modalState, setModalState] = useState<{
    open: boolean;
    type: "link" | "file";
    resource?: Resource | null;
  }>({ open: false, type: "link" });

  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { user } = useAuth();

  const planTier = (user as any)?.account?.plan_tier || "seedling";
  const limits = PLAN_LIMITS[planTier] || PLAN_LIMITS.seedling;

  const { data: resources, isLoading } = useQuery({
    queryKey: ["resources"],
    queryFn: () => resourceApi.list().then((res) => res.data),
  });

  const toggleMutation = useMutation({
    mutationFn: (id: number) => resourceApi.toggleActive(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["resources"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => resourceApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] });
      toast({ title: "Deleted", description: "Resource removed" });
    },
  });

  const links = (resources || []).filter((r) => r.type === "link");
  const files = (resources || []).filter((r) => r.type === "file");
  const items = activeTab === "links" ? links : files;
  const limit = activeTab === "links" ? limits.links : limits.files;
  const atLimit = items.length >= limit;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header — matches WorkflowsPage gradient pattern */}
      <div className="bg-gradient-to-r from-scurry-foam via-white to-scurry-orange-light -mx-2 sm:-mx-4 lg:-mx-6 -mt-3 sm:-mt-4 px-4 sm:px-6 lg:px-8 py-6 sm:py-8 rounded-b-2xl shadow-md border-b-2 border-scurry-orange/20 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-bl from-scurry-orange/10 to-transparent rounded-bl-full" />
        <div className="absolute bottom-0 left-0 w-24 h-24 bg-gradient-to-tr from-scurry-energy-burst/10 to-transparent rounded-tr-full" />
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-scurry-espresso font-display">
              Resources
            </h1>
            <span className="px-3 py-1 rounded-xl text-xs font-bold bg-scurry-yellow text-scurry-espresso capitalize">
              {planTier}
            </span>
          </div>
          <p className="text-sm sm:text-base text-scurry-latte mt-2">
            Your AI's ammo — links to hyperlink and PDFs to attach. Add descriptions so the AI knows when each is relevant.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2">
        {[
          { id: "links" as const, icon: Link2, label: "Links", count: links.length },
          { id: "files" as const, icon: FileText, label: "Files", count: files.length },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              activeTab === tab.id
                ? "bg-scurry-orange text-white shadow-sm"
                : "bg-white border border-scurry-gray-border text-scurry-latte hover:border-scurry-orange/30 hover:text-scurry-orange"
            }`}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
            <span className={`px-1.5 py-0.5 rounded-md text-[11px] font-bold ${
              activeTab === tab.id ? "bg-white/20 text-white" : "bg-scurry-gray-light text-scurry-gray-muted"
            }`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Limit bar + Add button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-32 bg-scurry-gray-border rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${atLimit ? "bg-scurry-red" : "bg-scurry-orange"}`}
              style={{ width: `${Math.min((items.length / limit) * 100, 100)}%` }}
            />
          </div>
          <span className="text-xs text-scurry-latte font-medium">
            {items.length} of {limit} {activeTab} used
          </span>
        </div>
        {!atLimit ? (
          <Button
            onClick={() => setModalState({ open: true, type: activeTab === "links" ? "link" : "file" })}
            className="bg-scurry-orange text-white hover:bg-scurry-orange-hover"
          >
            <Plus className="h-4 w-4 mr-1.5" />
            {activeTab === "links" ? "Add Link" : "Upload PDF"}
          </Button>
        ) : (
          <span className="text-xs text-scurry-orange font-semibold">Limit reached — upgrade for more</span>
        )}
      </div>

      {/* Resource list */}
      <div className="space-y-2">
        {items.map((resource) => (
          <ResourceRow
            key={resource.id}
            resource={resource}
            onToggle={() => toggleMutation.mutate(resource.id)}
            onEdit={() => setModalState({ open: true, type: resource.type as "link" | "file", resource })}
            onDelete={() => {
              if (window.confirm("Delete this resource? This can't be undone.")) {
                deleteMutation.mutate(resource.id);
              }
            }}
          />
        ))}
      </div>

      {/* Empty state */}
      {items.length === 0 && (
        <div className="p-8 border-2 border-dashed border-scurry-gray-border rounded-2xl text-center">
          <div className="text-3xl mb-3">{activeTab === "links" ? "🔗" : "📎"}</div>
          <p className="text-sm font-semibold text-scurry-espresso">No {activeTab} yet</p>
          <p className="text-xs text-scurry-gray-muted mt-1 mb-4">
            {activeTab === "links"
              ? "Add links your AI can hyperlink as CTAs in emails."
              : "Upload PDFs your AI can attach when relevant."}
          </p>
          {activeTab === "files" && limits.files === 0 && (
            <p className="text-xs text-scurry-orange font-semibold">PDF uploads require Oak plan or higher.</p>
          )}
        </div>
      )}

      {/* Info box */}
      <div className="p-5 bg-scurry-foam rounded-2xl border border-scurry-yellow/20">
        <div className="flex items-start gap-3">
          <span className="text-xl flex-shrink-0">🐿️</span>
          <div>
            <p className="text-sm font-bold text-scurry-espresso mb-1">How Resources Work</p>
            <p className="text-xs text-scurry-latte leading-relaxed">
              Resources live here as a library with descriptions. The AI reads each description to understand what it is.
              Then on each email component in your workflow, you choose <strong>how</strong> the AI uses each resource for
              that specific email — Always Include, AI Decides, or Custom Prompt. Same resource, different behavior per email.
            </p>
          </div>
        </div>
      </div>

      {/* Modal */}
      <ResourceModal
        open={modalState.open}
        onClose={() => setModalState({ open: false, type: "link", resource: null })}
        type={modalState.type}
        editResource={modalState.resource}
      />
    </div>
  );
};

export default ResourcesPage;