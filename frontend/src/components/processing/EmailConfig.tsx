/**
 * SCURRY FRONTEND UPDATE — EmailConfig.tsx
 * ========================================
 * REPLACES: frontend/src/components/processing/EmailConfig.tsx
 *
 * WHAT CHANGED (layout only — zero backend changes):
 * - AI Prompt section: was collapsible → now ALWAYS VISIBLE (no click needed)
 * - Send Timing section: was collapsible → now ALWAYS VISIBLE (no click needed)
 * - Delivery Settings + Skip Conditions + Pre-Send Check: were 3 separate
 *   collapsibles → now combined into 1 "Advanced Settings" collapsible
 * - RESOURCE LIBRARY: New sub-section inside Advanced Settings, between
 *   Skip Conditions and Timeline Check. Per-email, per-resource usage mode
 *   (AI Decides / Always / Custom Prompt / Off). Master toggle to enable/disable.
 *   Fetches resources from /api/resources. Saves config via component config payload.
 * - TIMELINE CHECK: New sub-section inside Advanced Settings, between
 *   Resources and Pre-Send Check. Reads contact timeline before sending.
 *   Default prompt auto-stops on replies/meetings/notes. Custom prompt option.
 *   Hover info icon shows default check rules.
 *
 * NET EFFECT: User needs 4 fewer clicks to configure an email component.
 *   Most-used sections (prompt + timing) visible immediately.
 *   Less-used sections (delivery, skip, resources, pre-send) one click away.
 *
 * BACKEND IMPACT: Requires new /api/resources endpoints + resources DB table.
 * - Existing API calls UNCHANGED (componentApi.updateConfig, testPreSendCheck, etc.)
 * - Save payload adds: resources_enabled (bool), resource_config (array)
 * - Custom events identical (save-configuration / configuration-saved)
 * - Form field names identical (react-hook-form register keys unchanged)
 * - Query keys: existing unchanged, NEW "resources" query key added
 *
 * Search for "SCURRY-CHANGE" to find structural changes.
 * Search for "RESOURCE" to find resource-related additions.
 * Search for "UNCHANGED" to verify untouched logic blocks.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Brain,
  Calendar,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  Edit3,
  ExternalLink,
  FileText,
  Info,
  Mail,
  Package,
  Settings,
  Shield,
  Sparkles,
  Timer,
  Zap,
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import VariableTextEditor from "@/components/ui/variable-text-editor";
import { Component, componentApi } from "@/lib/api";
import { resourceApi } from "@/lib/resourceApi";
import type { Resource, EmailResourceConfig, EmailResourceSettings } from "@/lib/resourceApi";
import {
  FIELD_DEFINITIONS,
  OPERATOR_OPTIONS,
  type Condition,
  type FieldDefinition,
} from "./shared/conditionConstants";
import { DataSourceTag, OperatorToggle } from "./shared/ConditionUI";
import { renderValueInput } from "./shared/ConditionValueInput";

interface EmailConfigProps {
  workflowId: number;
  component: Component;
}

interface EmailFormData {
  prompt: string;
  subject_prompt?: string;
  send_as?: "new_thread" | "reply_to_component";
  thread_parent_component_id?: string;
  send_timing: "immediate" | "fixed_delay" | "ai_decides";
  delay_value?: number;
  delay_unit?: "minutes" | "hours" | "days" | "weeks";
  ai_timing_context?: string;
  business_hours_only?: boolean;
  business_hours_start?: string;
  business_hours_end?: string;
  timezone?: string;
  skip_if_responded?: boolean;
  skip_if_meeting_scheduled?: boolean;
  skip_if_deal_closed?: boolean;
  skip_deal_stage?: string;
  skip_if_bounced?: boolean;
}

interface PreSendConditionGroup {
  id: string;
  operator: "AND" | "OR";
  conditions: Condition[];
}

type FailAction = "cancel_sequence" | "cancel_email" | "skip_proceed";

interface PreSendAIFilter {
  enabled: boolean;
  ai_prompt: string;
  condition_operator: string;
  condition_value: string;
  case_sensitive: boolean;
  if_fails: FailAction;
}

interface PreSendConfig {
  dataSource: string;
  groups: PreSendConditionGroup[];
  groupOperator: "AND" | "OR";
  crmIfFails: FailAction;
  aiFilter?: PreSendAIFilter;
}

// Variable Pill Component
const VariablePill: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-scurry-orange text-white rounded-xl text-xs font-semibold font-mono mx-0.5">
    <Sparkles className="h-3 w-3" />
    {children}
  </span>
);

// Timing Mode Card Component
interface TimingModeCardProps {
  isSelected: boolean;
  icon: React.ElementType;
  title: string;
  description: string;
  recommended?: boolean;
  onClick: () => void;
}

const TimingModeCard: React.FC<TimingModeCardProps> = ({
  isSelected,
  icon: Icon,
  title,
  description,
  recommended,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex-1 flex flex-col items-center gap-2 p-4 rounded-xl border-2 cursor-pointer relative transition-all ${
      isSelected
        ? "bg-scurry-orange/10 border-scurry-orange"
        : "bg-white border-scurry-foam hover:border-scurry-orange/30"
    }`}
  >
    {recommended && (
      <span className="absolute -top-2.5 right-2.5 px-2 py-0.5 bg-scurry-yellow text-scurry-espresso text-[10px] font-bold rounded-full">
        ⭐ BEST
      </span>
    )}
    <div
      className={`w-12 h-12 rounded-xl flex items-center justify-center ${
        isSelected ? "bg-scurry-orange" : "bg-scurry-foam"
      }`}
    >
      <Icon
        className={`h-6 w-6 ${isSelected ? "text-white" : "text-scurry-orange"}`}
      />
    </div>
    <span className="text-sm font-semibold text-scurry-espresso">{title}</span>
    <span className="text-xs text-scurry-latte text-center">{description}</span>
  </button>
);

// Collapsible Section Component
interface CollapsibleSectionProps {
  icon: React.ElementType;
  title: string;
  badge?: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  icon: Icon,
  title,
  badge,
  isOpen,
  onToggle,
  children,
}) => (
  <div className="bg-white rounded-xl border border-scurry-foam mb-5">
    <button
      type="button"
      onClick={onToggle}
      className="w-full flex items-center justify-between p-4 bg-scurry-foam/40 border-b border-scurry-foam cursor-pointer text-left rounded-t-xl"
    >
      <div className="flex items-center gap-2.5">
        <Icon className="h-[18px] w-[18px] text-scurry-orange" />
        <h3 className="text-[15px] font-semibold text-scurry-espresso">
          {title}
        </h3>
        {badge && (
          <span className="px-2.5 py-0.5 rounded-xl text-[11px] font-semibold bg-scurry-yellow text-scurry-espresso">
            {badge}
          </span>
        )}
      </div>
      {isOpen ? (
        <ChevronDown className="h-5 w-5 text-scurry-latte" />
      ) : (
        <ChevronRight className="h-5 w-5 text-scurry-latte" />
      )}
    </button>

    {isOpen && <div className="p-5">{children}</div>}
  </div>
);

const EmailConfig: React.FC<EmailConfigProps> = ({ workflowId, component }) => {
  // SCURRY-CHANGE: Prompt and Timing are now always visible (no expanded state needed)
  // Delivery + Skip + Pre-Send combined into single "Advanced Settings" collapsible
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [crmSubExpanded, setCrmSubExpanded] = useState(true);
  const [aiSubExpanded, setAiSubExpanded] = useState(true);
  const [crmTestState, setCrmTestState] = useState<
    "idle" | "loading" | "pass" | "fail"
  >("idle");
  const [crmTestReason, setCrmTestReason] = useState("");
  const [aiTestState, setAiTestState] = useState<
    "idle" | "loading" | "pass" | "fail"
  >("idle");
  const [aiTestReason, setAiTestReason] = useState("");

  const [preSendConfig, setPreSendConfig] = useState<PreSendConfig>(() => {
    const cfg = component.configuration;
    // Backward compat: convert old flat format to new multi-group format
    if (cfg?.pre_send_check) {
      const saved = cfg.pre_send_check;
      return {
        dataSource: saved.data_source || "pipedrive",
        groups: (saved.condition_groups || []).map((g: any) => ({
          id: g.id,
          operator: g.logic || "AND",
          conditions: g.conditions || [],
        })),
        groupOperator: saved.group_logic || "AND",
        crmIfFails: saved.crm_if_fails || "cancel_sequence",
        aiFilter: saved.ai_filter || undefined,
      };
    }
    if (cfg?.pre_send_check_field) {
      return {
        dataSource: "pipedrive",
        groups: [
          {
            id: "1",
            operator: "AND",
            conditions: [
              {
                id: "1",
                field: cfg.pre_send_check_field,
                operator: cfg.pre_send_check_operator || "equals",
                value: cfg.pre_send_check_value || "",
              },
            ],
          },
        ],
        groupOperator: "AND",
        crmIfFails: "cancel_sequence",
      };
    }
    return {
      dataSource: "pipedrive",
      groups: [],
      groupOperator: "AND",
      crmIfFails: "cancel_sequence",
    };
  });

  const [preSendFieldDefs, setPreSendFieldDefs] =
    useState<FieldDefinition[]>(FIELD_DEFINITIONS);

  const [isEditingPrompt, setIsEditingPrompt] = useState(false);
  const [isEditingSubjectPrompt, setIsEditingSubjectPrompt] = useState(false);
  const [copiedPrompt, setCopiedPrompt] = useState(false);
  const [copiedSubjectPrompt, setCopiedSubjectPrompt] = useState(false);

  // Resources state
  const [resourcesEnabled, setResourcesEnabled] = useState<boolean>(
    component.configuration?.resources_enabled ?? false,
  );
  const [resourceConfig, setResourceConfig] = useState<Record<string, { mode: string; customPrompt: string }>>(
    () => {
      const saved = component.configuration?.resource_config;
      if (saved && Array.isArray(saved)) {
        const map: Record<string, { mode: string; customPrompt: string }> = {};
        saved.forEach((rc: EmailResourceConfig) => {
          map[rc.resource_id] = { mode: rc.usage_mode, customPrompt: rc.custom_prompt || "" };
        });
        return map;
      }
      return {};
    },
  );
  const [expandedResource, setExpandedResource] = useState<number | null>(null);

  // Fresh Check (formerly "Timeline Check") is configured at the workflow
  // level now — see backend/workflows.py FreshCheckSettings and the
  // RagSettingsPanel component. The per-component state for the old
  // custom-prompt path is gone; the component only needs to know whether
  // a legacy custom prompt was set so it can prompt the admin to migrate
  // it into a dedicated AI Filter component (#178 T5 migration banner).
  const legacyTimelineCustomEnabled = Boolean(
    component.configuration?.timeline_custom_enabled,
  );
  const legacyTimelineCustomPrompt =
    (component.configuration?.timeline_custom_prompt as string | undefined) ??
    "";

  const queryClient = useQueryClient();

  // Fetch available variables from previous components
  const { data: availableVariables } = useQuery({
    queryKey: ["component-variables", component.id],
    queryFn: async () => {
      const response = await componentApi.getAvailableVariables(component.id);
      return response.data.available_variables;
    },
  });

  const { data: workflowComponents } = useQuery({
    queryKey: ["components", workflowId],
    queryFn: async () => {
      const response = await componentApi.getByWorkflow(workflowId);
      return response.data;
    },
    enabled: !!workflowId,
  });

  // Fetch Pipedrive stages
  const { data: stagesData } = useQuery({
    queryKey: ["pipedrive-stages"],
    queryFn: async () => {
      const response = await componentApi.getPipedriveStages();
      return response.data;
    },
    staleTime: 10 * 60 * 1000,
  });

  // Fetch Pipedrive users (for pre-send check owner_name field)
  const { data: usersData } = useQuery({
    queryKey: ["pipedrive-users"],
    queryFn: async () => {
      const response = await componentApi.getPipedriveUsers();
      return response.data;
    },
    staleTime: 10 * 60 * 1000,
  });

  // Fetch Pipedrive currencies (for pre-send check currency field)
  const { data: currenciesData } = useQuery({
    queryKey: ["pipedrive-currencies"],
    queryFn: async () => {
      const response = await componentApi.getPipedriveCurrencies();
      return response.data;
    },
    staleTime: 10 * 60 * 1000,
  });

  // Fetch account resources for the Resources section
  const { data: accountResources } = useQuery({
    queryKey: ["resources"],
    queryFn: async () => {
      const response = await resourceApi.list();
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Active resources only
  const activeResources = (accountResources || []).filter((r: Resource) => r.is_active);

  // Pre-send check test handlers
  const handleCrmTest = async () => {
    setCrmTestState("loading");
    setCrmTestReason("");
    try {
      const response = await componentApi.testPreSendCheck({
        test_type: "crm",
        component_id: component.id,
        condition_groups: preSendConfig.groups.map((g) => ({
          id: g.id,
          logic: g.operator,
          conditions: g.conditions.filter((c) => c.field),
        })),
        group_logic: preSendConfig.groupOperator,
        data_source: preSendConfig.dataSource,
      });
      const data = response.data;
      setCrmTestState(data.passed ? "pass" : "fail");
      setCrmTestReason(data.reason);
    } catch (err: any) {
      setCrmTestState("fail");
      setCrmTestReason(
        err?.response?.data?.detail || err.message || "Test failed",
      );
    }
  };

  const handleAiTest = async () => {
    setAiTestState("loading");
    setAiTestReason("");
    try {
      const af = preSendConfig.aiFilter;
      if (!af) return;
      const response = await componentApi.testPreSendCheck({
        test_type: "ai_filter",
        component_id: component.id,
        ai_prompt: af.ai_prompt,
        condition_operator: af.condition_operator,
        condition_value: af.condition_value,
        case_sensitive: af.case_sensitive,
      });
      const data = response.data;
      setAiTestState(data.passed ? "pass" : "fail");
      setAiTestReason(data.reason);
    } catch (err: any) {
      setAiTestState("fail");
      setAiTestReason(
        err?.response?.data?.detail || err.message || "Test failed",
      );
    }
  };

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<EmailFormData>({
    defaultValues: {
      prompt: "",
      subject_prompt: "",
      send_as: "new_thread",
      thread_parent_component_id: "",
      send_timing: "immediate",
      delay_value: 1,
      delay_unit: "days",
      ai_timing_context: "",
      business_hours_only: true,
      business_hours_start: "09:00",
      business_hours_end: "17:00",
      timezone: "America/New_York",
      skip_if_responded: false,
      skip_if_meeting_scheduled: true,
      skip_if_deal_closed: false,
      skip_deal_stage: "won",
      skip_if_bounced: false,
      ...component.configuration,
    },
  });

  const watchedValues = watch();
  const sendTiming = watchedValues.send_timing;
  const sendAs = watchedValues.send_as || "new_thread";
  const isThreadedReply = sendAs === "reply_to_component";
  const hasParentDeletedWarning =
    component.configuration?.threading_warning_code === "parent_deleted" &&
    sendAs === "new_thread";
  const deletedParentName =
    component.configuration?.threading_warning_parent_component_name;
  const priorEmailComponents = (workflowComponents || [])
    .filter(
      (candidate) =>
        candidate.type === "email" &&
        candidate.id !== component.id &&
        candidate.order < component.order,
    )
    .sort((a, b) => a.order - b.order);
  const selectedThreadParent = priorEmailComponents.find(
    (candidate) => String(candidate.id) === String(watchedValues.thread_parent_component_id || ""),
  );

  useEffect(() => {
    if (component.configuration) {
      Object.entries(component.configuration).forEach(([key, value]) => {
        setValue(key as keyof EmailFormData, value);
      });
    }
  }, [component.configuration, setValue]);

  useEffect(() => {
    if (sendAs === "new_thread" && watchedValues.thread_parent_component_id) {
      setValue("thread_parent_component_id", "");
    }
  }, [sendAs, watchedValues.thread_parent_component_id, setValue]);

  useEffect(() => {
    if (!isThreadedReply) return;
    const currentParentId = String(watchedValues.thread_parent_component_id || "");
    if (!currentParentId) return;
    const stillValid = priorEmailComponents.some(
      (candidate) => String(candidate.id) === currentParentId,
    );
    if (!stillValid) {
      setValue("send_as", "new_thread");
      setValue("thread_parent_component_id", "");
    }
  }, [
    isThreadedReply,
    watchedValues.thread_parent_component_id,
    priorEmailComponents,
    setValue,
  ]);

  // Update pre-send check field definitions when Pipedrive data loads
  useEffect(() => {
    if (stagesData?.stages_by_pipeline) {
      setPreSendFieldDefs((prev) =>
        prev.map((field) => {
          if (field.value === "stage") {
            const grouped: Record<
              string,
              Array<{ value: string; label: string }>
            > = {};
            Object.entries(stagesData.stages_by_pipeline).forEach(
              ([, pipelineData]: [string, any]) => {
                const pipelineName = pipelineData.pipeline_name;
                grouped[pipelineName] = pipelineData.stages.map(
                  (stage: any) => ({
                    value: stage.id,
                    label: stage.name,
                  }),
                );
              },
            );
            return { ...field, grouped_options: grouped };
          }
          return field;
        }),
      );
    }
  }, [stagesData]);

  useEffect(() => {
    if (usersData?.users) {
      setPreSendFieldDefs((prev) =>
        prev.map((field) =>
          field.value === "owner_name"
            ? { ...field, options: usersData.users }
            : field,
        ),
      );
    }
  }, [usersData]);

  useEffect(() => {
    if (currenciesData?.currencies) {
      setPreSendFieldDefs((prev) =>
        prev.map((field) =>
          field.value === "currency"
            ? { ...field, options: currenciesData.currencies }
            : field,
        ),
      );
    }
  }, [currenciesData]);

  const updateConfigMutation = useMutation({
    mutationFn: (config: any) =>
      componentApi.updateConfig(component.id, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      const event = new CustomEvent("configuration-saved", {
        detail: { componentId: component.id, success: true },
      });
      window.dispatchEvent(event);
    },
    onError: (error: any) => {
      const errorDetail =
        error?.response?.data?.detail ||
        error?.message ||
        "Failed to save configuration.";
      const event = new CustomEvent("configuration-saved", {
        detail: { componentId: component.id, success: false, error: errorDetail },
      });
      window.dispatchEvent(event);
    },
  });

  // Listen for save-configuration event from parent
  // Use a ref so the event handler always calls the latest onSubmit (set after declaration below)
  const onSubmitRef = React.useRef<((data: EmailFormData) => Promise<void>) | null>(null);

  // Pre-send check handlers
  const addPreSendCondition = (groupId: string) => {
    setPreSendConfig((prev) => ({
      ...prev,
      groups: prev.groups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              conditions: [
                ...group.conditions,
                {
                  id: Date.now().toString(),
                  field: "",
                  operator: "equals",
                  value: "",
                },
              ],
            }
          : group,
      ),
    }));
  };

  const removePreSendCondition = (groupId: string, conditionId: string) => {
    setPreSendConfig((prev) => ({
      ...prev,
      groups: prev.groups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              conditions: group.conditions.filter((c) => c.id !== conditionId),
            }
          : group,
      ),
    }));
  };

  const updatePreSendCondition = (
    groupId: string,
    conditionId: string,
    field: keyof Condition,
    value: string,
  ) => {
    setPreSendConfig((prev) => ({
      ...prev,
      groups: prev.groups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              conditions: group.conditions.map((c) =>
                c.id === conditionId ? { ...c, [field]: value } : c,
              ),
            }
          : group,
      ),
    }));
  };

  const addPreSendGroup = () => {
    setPreSendConfig((prev) => ({
      ...prev,
      groups: [
        ...prev.groups,
        {
          id: Date.now().toString(),
          operator: "AND",
          conditions: [
            {
              id: (Date.now() + 1).toString(),
              field: "",
              operator: "equals",
              value: "",
            },
          ],
        },
      ],
    }));
  };

  const removePreSendGroup = (groupId: string) => {
    setPreSendConfig((prev) => ({
      ...prev,
      groups: prev.groups.filter((g) => g.id !== groupId),
    }));
  };

  const togglePreSendGroupOperator = (groupId: string) => {
    setPreSendConfig((prev) => ({
      ...prev,
      groups: prev.groups.map((group) =>
        group.id === groupId
          ? { ...group, operator: group.operator === "AND" ? "OR" : "AND" }
          : group,
      ),
    }));
  };

  const togglePreSendGlobalOperator = () => {
    setPreSendConfig((prev) => ({
      ...prev,
      groupOperator: prev.groupOperator === "AND" ? "OR" : "AND",
    }));
  };

  const onSubmit = async (data: EmailFormData) => {
    // Build the save payload: merge form data with pre-send config (new format)
    const payload: any = { ...data };
    payload.send_as = data.send_as || "new_thread";
    payload.thread_parent_component_id =
      payload.send_as === "reply_to_component" && data.thread_parent_component_id
        ? Number(data.thread_parent_component_id)
        : null;
    if (payload.send_as === "reply_to_component") {
      payload.subject_prompt = "";
    }
    // One-time warning metadata (set when a parent email was deleted).
    // Clear on save after the user has seen/acted on it in the editor.
    delete payload.threading_warning_code;
    delete payload.threading_warning_parent_component_id;
    delete payload.threading_warning_parent_component_name;
    // Remove old flat fields if present (backward compat cleanup)
    delete payload.pre_send_check_field;
    delete payload.pre_send_check_operator;
    delete payload.pre_send_check_value;

    // Write new format if there are condition groups or AI filter enabled
    const hasConditions = preSendConfig.groups.some((g) =>
      g.conditions.some((c) => c.field),
    );
    const hasAIFilter =
      preSendConfig.aiFilter?.enabled && preSendConfig.aiFilter?.ai_prompt;
    if (hasConditions || hasAIFilter) {
      payload.pre_send_check = {
        data_source: preSendConfig.dataSource,
        condition_groups: preSendConfig.groups.map((g) => ({
          id: g.id,
          logic: g.operator,
          conditions: g.conditions,
        })),
        group_logic: preSendConfig.groupOperator,
        crm_if_fails: preSendConfig.crmIfFails,
        ...(hasAIFilter ? { ai_filter: preSendConfig.aiFilter } : {}),
      };
    } else {
      payload.pre_send_check = null;
    }

    // Resources config
    payload.resources_enabled = resourcesEnabled;
    payload.resource_config = Object.entries(resourceConfig).map(
      ([resourceId, cfg]) => ({
        resource_id: resourceId,
        usage_mode: cfg.mode,
        custom_prompt: cfg.mode === "custom_prompt" ? cfg.customPrompt : null,
      }),
    );

    // Fresh Check (#178 T5): per-component Timeline Check config is
    // retired. Rules live on workflow.rag_settings.fresh_check instead
    // — see RagSettingsPanel. We preserve any legacy fields the admin
    // hasn't migrated (so the banner can surface the old custom prompt)
    // by leaving them untouched in `payload`.

    await updateConfigMutation.mutateAsync(payload);
    setIsEditingPrompt(false);
    setIsEditingSubjectPrompt(false);
  };

  // Wire up the save-configuration event listener (must be after onSubmit declaration)
  onSubmitRef.current = onSubmit;

  useEffect(() => {
    const handleSaveEvent = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.componentId === component.id) {
        handleSubmit((data) => onSubmitRef.current?.(data) ?? Promise.resolve())();
      }
    };

    window.addEventListener("save-configuration", handleSaveEvent);
    return () => {
      window.removeEventListener("save-configuration", handleSaveEvent);
    };
  }, [component.id, handleSubmit]);

  // Copy handlers
  const handleCopy = (type: "prompt" | "subject") => {
    const text =
      type === "prompt" ? watchedValues.prompt : watchedValues.subject_prompt;
    navigator.clipboard.writeText(text || "");
    if (type === "prompt") {
      setCopiedPrompt(true);
      setTimeout(() => setCopiedPrompt(false), 2000);
    } else {
      setCopiedSubjectPrompt(true);
      setTimeout(() => setCopiedSubjectPrompt(false), 2000);
    }
  };

  // Render prompt content with variable pills
  const renderPromptWithPills = (text: string | undefined) => {
    if (!text) {
      return (
        <span className="text-scurry-latte italic">No prompt configured</span>
      );
    }

    const parts = text.split(/(\{\{[^}]+\}\})/g);
    return parts.map((part, idx) => {
      if (part.match(/^\{\{[^}]+\}\}$/)) {
        const varName = part.slice(2, -2);
        return <VariablePill key={idx}>{varName}</VariablePill>;
      }
      return (
        <span key={idx} className="whitespace-pre-wrap">
          {part}
        </span>
      );
    });
  };

  // Check if CRM conditions are configured
  const crmEnabled = preSendConfig.groups.some((g) =>
    g.conditions.some((c) => c.field),
  );

  // Count active skip conditions
  const activeSkipCount = [
    watchedValues.skip_if_responded,
    watchedValues.skip_if_meeting_scheduled,
    watchedValues.skip_if_deal_closed,
    watchedValues.skip_if_bounced,
  ].filter(Boolean).length;

  return (
    <div className="space-y-5">
      {/* Info Bar */}
      <div className="bg-scurry-foam p-3 rounded-xl text-sm text-scurry-latte flex items-center gap-2">
        <Mail className="h-4 w-4 text-scurry-orange flex-shrink-0" />
        Create personalized follow-up emails from your meeting transcripts! 📧
      </div>

      {/* AI Prompt Configuration — SCURRY-CHANGE: Always visible, no collapse needed */}
      <div className="bg-white rounded-xl border border-scurry-foam mb-5">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-0 mb-4">
          <Brain className="h-[18px] w-[18px] text-scurry-orange" />
          <h3 className="text-[15px] font-semibold text-scurry-espresso">
            AI Prompt Configuration
          </h3>
          <span className="px-2.5 py-0.5 rounded-xl text-[11px] font-semibold bg-scurry-yellow text-scurry-espresso">
            Required
          </span>
        </div>
        <div className="px-5 pb-5">
          {/* Email Body Prompt */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-3">
              <Label className="text-sm font-semibold text-scurry-espresso flex items-center gap-2">
                <FileText className="h-4 w-4 text-scurry-orange" />
                Email Body Prompt
              </Label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleCopy("prompt")}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-scurry-latte hover:text-scurry-espresso rounded"
                >
                  {copiedPrompt ? (
                    <Check className="h-3.5 w-3.5 text-scurry-green" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  {copiedPrompt ? "Copied!" : "Copy"}
                </button>
                <button
                  type="button"
                  onClick={() => setIsEditingPrompt(!isEditingPrompt)}
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded ${
                    isEditingPrompt
                      ? "bg-scurry-orange text-white"
                      : "bg-scurry-foam text-scurry-espresso hover:bg-scurry-orange/10"
                  }`}
                >
                  <Edit3 className="h-3.5 w-3.5" />
                  {isEditingPrompt ? "Done" : "Edit"}
                </button>
              </div>
            </div>

            {isEditingPrompt ? (
              <div className="space-y-2">
                <VariableTextEditor
                  value={watchedValues.prompt || ""}
                  onChange={(value) => setValue("prompt", value)}
                  workflowId={workflowId}
                  componentId={component.id}
                  rows={8}
                  placeholder="Write your email body prompt here. Use {{variable}} to insert variables."
                />
                {availableVariables && availableVariables.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    <span className="text-xs text-scurry-latte font-medium">
                      Insert:
                    </span>
                    {availableVariables.map((variable: any) => (
                      <button
                        key={variable.value}
                        type="button"
                        onClick={() =>
                          setValue(
                            "prompt",
                            (watchedValues.prompt || "") +
                              `{{${variable.value}}}`,
                          )
                        }
                        className="px-2 py-1 text-xs font-mono bg-scurry-foam hover:bg-scurry-orange/10 text-scurry-espresso rounded border border-transparent hover:border-scurry-orange/30 transition-colors"
                      >
                        {`{{${variable.label}}}`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 bg-scurry-foam/50 rounded-lg text-sm text-scurry-espresso leading-relaxed">
                {renderPromptWithPills(watchedValues.prompt)}
              </div>
            )}
            {errors.prompt && (
              <p className="text-xs text-red-600 mt-1">
                This field is required
              </p>
            )}
          </div>

          {/* Subject Line Prompt */}
          {!isThreadedReply && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <Label className="text-sm font-semibold text-scurry-espresso flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-scurry-orange" />
                Subject Line Prompt
                <Badge variant="outline" className="text-[10px] ml-1">
                  Optional
                </Badge>
              </Label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => handleCopy("subject")}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-scurry-latte hover:text-scurry-espresso rounded"
                >
                  {copiedSubjectPrompt ? (
                    <Check className="h-3.5 w-3.5 text-scurry-green" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  {copiedSubjectPrompt ? "Copied!" : "Copy"}
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setIsEditingSubjectPrompt(!isEditingSubjectPrompt)
                  }
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded ${
                    isEditingSubjectPrompt
                      ? "bg-scurry-orange text-white"
                      : "bg-scurry-foam text-scurry-espresso hover:bg-scurry-orange/10"
                  }`}
                >
                  <Edit3 className="h-3.5 w-3.5" />
                  {isEditingSubjectPrompt ? "Done" : "Edit"}
                </button>
              </div>
            </div>

            {isEditingSubjectPrompt ? (
              <div className="space-y-2">
                <VariableTextEditor
                  value={watchedValues.subject_prompt || ""}
                  onChange={(value) => setValue("subject_prompt", value)}
                  workflowId={workflowId}
                  componentId={component.id}
                  rows={3}
                  placeholder="Write your subject line prompt here."
                />
                {availableVariables && availableVariables.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    <span className="text-xs text-scurry-latte font-medium">
                      Insert:
                    </span>
                    {availableVariables.slice(0, 5).map((variable: any) => (
                      <button
                        key={variable.value}
                        type="button"
                        onClick={() =>
                          setValue(
                            "subject_prompt",
                            (watchedValues.subject_prompt || "") +
                              `{{${variable.value}}}`,
                          )
                        }
                        className="px-2 py-1 text-xs font-mono bg-scurry-foam hover:bg-scurry-orange/10 text-scurry-espresso rounded border border-transparent hover:border-scurry-orange/30 transition-colors"
                      >
                        {`{{${variable.label}}}`}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4 bg-scurry-foam/50 rounded-lg text-sm text-scurry-espresso">
                {renderPromptWithPills(watchedValues.subject_prompt)}
              </div>
            )}
          </div>
          )}
        </div>
      </div>

      {/* Send Timing — SCURRY-CHANGE: Always visible, no collapse needed */}
      <div className="bg-white rounded-xl border border-scurry-foam mb-5">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-0 mb-4">
          <Clock className="h-[18px] w-[18px] text-scurry-orange" />
          <h3 className="text-[15px] font-semibold text-scurry-espresso">
            Send Timing
          </h3>
          {sendTiming === "ai_decides" && (
            <span className="px-2.5 py-0.5 rounded-xl text-[11px] font-semibold bg-scurry-yellow text-scurry-espresso">
              AI Optimized
            </span>
          )}
        </div>
        <div className="px-5 pb-5">
          <p className="text-sm text-scurry-latte mb-4">
            Choose when the email should be sent after the workflow trigger.
          </p>

          {/* Timing Mode Cards */}
          <div className="flex gap-3 mb-6">
            <TimingModeCard
              isSelected={sendTiming === "immediate"}
              icon={Zap}
              title="Immediate"
              description="Send right away"
              onClick={() => setValue("send_timing", "immediate")}
            />
            <TimingModeCard
              isSelected={sendTiming === "fixed_delay"}
              icon={Timer}
              title="Fixed Delay"
              description="Wait set time"
              onClick={() => setValue("send_timing", "fixed_delay")}
            />
            <TimingModeCard
              isSelected={sendTiming === "ai_decides"}
              icon={Brain}
              title="AI Decides"
              description="Smart timing"
              recommended
              onClick={() => setValue("send_timing", "ai_decides")}
            />
          </div>

          {/* Fixed Delay Settings */}
          {sendTiming === "fixed_delay" && (
            <div className="p-4 bg-scurry-foam/50 rounded-lg">
              <Label className="text-sm font-medium text-scurry-espresso mb-3 block">
                Wait Time
              </Label>
              <div className="flex items-center gap-3">
                <Input
                  type="number"
                  min={1}
                  {...register("delay_value", { valueAsNumber: true })}
                  className="w-20"
                />
                <Select
                  value={watchedValues.delay_unit}
                  onValueChange={(value) =>
                    setValue("delay_unit", value as any)
                  }
                >
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="minutes">Minutes</SelectItem>
                    <SelectItem value="hours">Hours</SelectItem>
                    <SelectItem value="days">Days</SelectItem>
                    <SelectItem value="weeks">Weeks</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* AI Timing Settings */}
          {sendTiming === "ai_decides" && (
            <div className="p-4 bg-scurry-orange/5 border border-scurry-orange/20 rounded-lg">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="h-4 w-4 text-scurry-orange" />
                <span className="text-sm font-semibold text-scurry-espresso">
                  AI Timing Context
                </span>
                <Badge variant="outline" className="text-[10px]">
                  Optional
                </Badge>
              </div>
              <VariableTextEditor
                value={watchedValues.ai_timing_context || ""}
                onChange={(value) => setValue("ai_timing_context", value)}
                workflowId={workflowId}
                componentId={component.id}
                rows={3}
                placeholder="E.g., 'If the prospect mentioned they are traveling, wait until they return.'"
              />
              {availableVariables && availableVariables.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  <span className="text-xs text-scurry-latte font-medium">
                    Insert:
                  </span>
                  {availableVariables.slice(0, 5).map((variable: any) => (
                    <button
                      key={variable.value}
                      type="button"
                      onClick={() =>
                        setValue(
                          "ai_timing_context",
                          (watchedValues.ai_timing_context || "") +
                            `{{${variable.value}}}`,
                        )
                      }
                      className="px-2 py-1 text-xs font-mono bg-scurry-foam hover:bg-scurry-orange/10 text-scurry-espresso rounded border border-transparent hover:border-scurry-orange/30 transition-colors"
                    >
                      {`{{${variable.label}}}`}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Same-thread sending */}
      <div className="bg-white rounded-xl border border-scurry-foam mb-5">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-0 mb-4">
          <Mail className="h-[18px] w-[18px] text-scurry-orange" />
          <h3 className="text-[15px] font-semibold text-scurry-espresso">
            Send As
          </h3>
        </div>
        <div className="px-5 pb-5 space-y-4">
          <p className="text-sm text-scurry-latte">
            Choose whether this email starts a new conversation or replies on an earlier email thread.
          </p>

          {hasParentDeletedWarning && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <span>
                  Parent email component
                  {deletedParentName ? ` "${deletedParentName}"` : ""} was deleted.
                  This step was reverted to <strong>New thread</strong>.
                </span>
              </div>
            </div>
          )}

          <Select
            value={sendAs}
            onValueChange={(value) => setValue("send_as", value as "new_thread" | "reply_to_component")}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="new_thread">New thread</SelectItem>
              <SelectItem
                value="reply_to_component"
                disabled={priorEmailComponents.length === 0}
              >
                Reply to prior email
              </SelectItem>
            </SelectContent>
          </Select>

          {isThreadedReply && (
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium text-scurry-espresso mb-2 block">
                  Reply To
                </Label>
                <Select
                  value={String(watchedValues.thread_parent_component_id || "")}
                  onValueChange={(value) => setValue("thread_parent_component_id", value)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select an earlier email component" />
                  </SelectTrigger>
                  <SelectContent>
                    {priorEmailComponents.map((candidate) => (
                      <SelectItem key={candidate.id} value={String(candidate.id)}>
                        {candidate.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="rounded-lg border border-scurry-orange/20 bg-scurry-orange/5 px-4 py-3 text-sm text-scurry-espresso">
                This email will send as a reply in the same thread.
                {selectedThreadParent ? ` It will reply to "${selectedThreadParent.name}".` : ""}
                {" "}No subject line will be generated unless threading falls back to a new thread at send time.
              </div>
            </div>
          )}

          {!isThreadedReply && priorEmailComponents.length === 0 && (
            <div className="rounded-lg border border-dashed border-scurry-gray-border bg-scurry-foam/40 px-4 py-3 text-sm text-scurry-latte">
              Add at least one earlier email component in this workflow to enable threaded replies.
            </div>
          )}
        </div>
      </div>

      {/* SCURRY-CHANGE: Delivery + Skip + Pre-Send combined into single "Advanced Settings" */}
      <CollapsibleSection
        icon={Settings}
        title="Advanced Settings"
        badge={
          activeSkipCount > 0 || crmEnabled || preSendConfig.aiFilter?.enabled || resourcesEnabled || legacyTimelineCustomEnabled
            ? "Configured"
            : undefined
        }
        isOpen={advancedExpanded}
        onToggle={() => setAdvancedExpanded(!advancedExpanded)}
      >
        {/* ── Delivery Settings sub-section ── */}
        <div className="flex items-center gap-2 mb-3">
          <Calendar className="h-4 w-4 text-scurry-orange" />
          <h4 className="text-[13px] font-bold text-scurry-espresso">
            Delivery Settings
          </h4>
        </div>
        <div className="space-y-4">
          {/* Business Hours */}
          <div className="flex items-center justify-between p-3 bg-scurry-foam/50 rounded-lg">
            <div className="flex items-center gap-3">
              <Clock className="h-4 w-4 text-scurry-orange" />
              <div>
                <p className="text-sm font-medium text-scurry-espresso">
                  Business Hours Only
                </p>
                <p className="text-xs text-scurry-latte">
                  Only send emails during work hours
                </p>
              </div>
            </div>
            <Switch
              checked={watchedValues.business_hours_only}
              onCheckedChange={(checked) =>
                setValue("business_hours_only", checked)
              }
            />
          </div>

          {watchedValues.business_hours_only && (
            <div className="grid grid-cols-2 gap-4 pl-4">
              <div>
                <Label className="text-xs text-scurry-latte mb-1 block">
                  Start Time
                </Label>
                <Input type="time" {...register("business_hours_start")} />
              </div>
              <div>
                <Label className="text-xs text-scurry-latte mb-1 block">
                  End Time
                </Label>
                <Input type="time" {...register("business_hours_end")} />
              </div>
            </div>
          )}

          {/* Timezone */}
          <div className="flex items-center justify-between p-3 bg-scurry-foam/50 rounded-lg">
            <div>
              <p className="text-sm font-medium text-scurry-espresso">
                Timezone
              </p>
              <p className="text-xs text-scurry-latte">
                Respect recipient's timezone
              </p>
            </div>
            <Select
              value={watchedValues.timezone}
              onValueChange={(value) => setValue("timezone", value)}
            >
              <SelectTrigger className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="America/New_York">
                  Eastern (New York)
                </SelectItem>
                <SelectItem value="America/Chicago">
                  Central (Chicago)
                </SelectItem>
                <SelectItem value="America/Denver">
                  Mountain (Denver)
                </SelectItem>
                <SelectItem value="America/Los_Angeles">
                  Pacific (Los Angeles)
                </SelectItem>
                <SelectItem value="Europe/London">London</SelectItem>
                <SelectItem value="Europe/Paris">Paris</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        {/* ── Divider ── */}
        <div className="h-px bg-scurry-gray-border -mx-5 my-5" />

        {/* ── Skip Conditions sub-section ── */}
        <div className="flex items-center gap-2 mb-3">
          <Shield className="h-4 w-4 text-scurry-orange" />
          <h4 className="text-[13px] font-bold text-scurry-espresso">
            Skip Conditions
          </h4>
          {activeSkipCount > 0 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-scurry-orange-light text-scurry-orange">
              {activeSkipCount} Active
            </span>
          )}
        </div>
        <p className="text-sm text-scurry-latte mb-4">
          Don't send this email when these conditions are met:
        </p>

        <div className="space-y-3">
          {/* Skip if responded */}
          <label className="flex items-start gap-3 p-3 rounded-lg cursor-pointer hover:bg-scurry-foam/30 transition-colors">
            <Checkbox
              checked={watchedValues.skip_if_responded}
              onCheckedChange={(checked) =>
                setValue("skip_if_responded", !!checked)
              }
            />
            <div>
              <p className="text-sm font-medium text-scurry-espresso">
                If recipient responded
              </p>
              <p className="text-xs text-scurry-latte">
                Don't send if they already replied
              </p>
            </div>
          </label>

          {/* Skip if meeting scheduled */}
          <label className="flex items-start gap-3 p-3 rounded-lg cursor-pointer hover:bg-scurry-foam/30 transition-colors">
            <Checkbox
              checked={watchedValues.skip_if_meeting_scheduled}
              onCheckedChange={(checked) =>
                setValue("skip_if_meeting_scheduled", !!checked)
              }
            />
            <div>
              <p className="text-sm font-medium text-scurry-espresso">
                If meeting scheduled
              </p>
              <p className="text-xs text-scurry-latte">
                Skip if a meeting is booked with the contact
              </p>
            </div>
          </label>

          {/* Skip if deal stage changed */}
          <label className="flex items-start gap-3 p-3 rounded-lg cursor-pointer hover:bg-scurry-foam/30 transition-colors">
            <Checkbox
              checked={watchedValues.skip_if_deal_closed}
              onCheckedChange={(checked) =>
                setValue("skip_if_deal_closed", !!checked)
              }
            />
            <div>
              <p className="text-sm font-medium text-scurry-espresso">
                If deal stage changes
              </p>
              <p className="text-xs text-scurry-latte">
                Skip when deal moves to specific stage
              </p>
            </div>
          </label>

          {watchedValues.skip_if_deal_closed && (
            <div className="ml-8">
              <Select
                value={watchedValues.skip_deal_stage}
                onValueChange={(value) => setValue("skip_deal_stage", value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select stage..." />
                </SelectTrigger>
                <SelectContent>
                  {stagesData?.stages_by_pipeline ? (
                    Object.entries(stagesData.stages_by_pipeline).map(
                      ([pipelineId, pipelineData]: [string, any]) => (
                        <SelectGroup key={pipelineId}>
                          <SelectLabel>
                            {pipelineData.pipeline_name}
                          </SelectLabel>
                          {pipelineData.stages.map((stage: any) => (
                            <SelectItem key={stage.id} value={stage.id}>
                              {stage.name}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      ),
                    )
                  ) : (
                    <>
                      <SelectItem value="won">Won</SelectItem>
                      <SelectItem value="lost">Lost</SelectItem>
                      <SelectItem value="qualified">Qualified</SelectItem>
                    </>
                  )}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* Skip if bounced */}
          <label className="flex items-start gap-3 p-3 rounded-lg cursor-pointer hover:bg-scurry-foam/30 transition-colors">
            <Checkbox
              checked={watchedValues.skip_if_bounced}
              onCheckedChange={(checked) =>
                setValue("skip_if_bounced", !!checked)
              }
            />
            <div>
              <p className="text-sm font-medium text-scurry-espresso">
                If email bounced
              </p>
              <p className="text-xs text-scurry-latte">
                Skip if the email address is invalid
              </p>
            </div>
          </label>
        </div>
        {/* ── Divider ── */}
        <div className="h-px bg-scurry-gray-border -mx-5 my-5" />

        {/* ── Resources sub-section ── */}
        <div className="flex items-center gap-2 mb-3">
          <Package className="h-4 w-4 text-scurry-orange" />
          <h4 className="text-[13px] font-bold text-scurry-espresso">
            Resources
          </h4>
          {resourcesEnabled && activeResources.length > 0 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-scurry-orange-light text-scurry-orange">
              {Object.values(resourceConfig).filter((c) => c.mode !== "disabled").length} Active
            </span>
          )}
        </div>
        <p className="text-sm text-scurry-latte mb-4">
          Control how each resource is used in this specific email. Click a resource to configure.
        </p>

        {/* Resources master toggle */}
        <div className="flex items-center justify-between p-3 bg-scurry-foam/50 rounded-lg mb-3">
          <div className="flex items-center gap-3">
            <span className="text-base">🔗</span>
            <div>
              <p className="text-sm font-medium text-scurry-espresso">
                Enable Resources for This Email
              </p>
              <p className="text-xs text-scurry-latte">
                AI can hyperlink CTAs and attach PDFs from your Resource library
              </p>
            </div>
          </div>
          <Switch
            checked={resourcesEnabled}
            onCheckedChange={(checked) => setResourcesEnabled(checked)}
          />
        </div>

        {resourcesEnabled && (
          <div className="space-y-2">
            {activeResources.length === 0 && (
              <div className="p-4 rounded-lg border border-dashed border-scurry-gray-border text-center">
                <p className="text-xs text-scurry-gray-muted">No active resources.</p>
                <a
                  href="/resources"
                  className="inline-flex items-center gap-1 text-xs text-scurry-orange font-medium mt-1 hover:underline"
                >
                  Add Resources <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}

            {activeResources.map((resource: Resource) => {
              const config = resourceConfig[resource.id] || { mode: "ai_decides", customPrompt: "" };
              const isExpanded = expandedResource === resource.id;
              const isOff = config.mode === "disabled";
              const modeLabels: Record<string, string> = {
                ai_decides: "🤖 AI Decides",
                always: "📌 Always",
                custom_prompt: "💡 Custom",
                disabled: "⛔ Off",
              };
              const modeBgColors: Record<string, string> = {
                ai_decides: "bg-scurry-orange-light text-scurry-orange",
                always: "bg-scurry-green-light text-scurry-green",
                custom_prompt: "bg-scurry-blue-bg text-scurry-blue-text",
                disabled: "bg-scurry-gray-light text-scurry-gray-muted",
              };

              return (
                <div
                  key={resource.id}
                  className={`border rounded-lg overflow-hidden transition-all ${
                    isOff
                      ? "border-scurry-gray-light opacity-55"
                      : "border-scurry-gray-border"
                  }`}
                >
                  {/* Row header — clickable to expand */}
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedResource(isExpanded ? null : resource.id)
                    }
                    className="w-full flex items-center gap-2.5 p-3 text-left cursor-pointer hover:bg-scurry-foam/30 transition-colors"
                  >
                    <span className="text-sm">
                      {resource.type === "link" ? "🔗" : "📎"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[13px] font-semibold text-scurry-espresso truncate">
                        {resource.label}
                      </p>
                      {resource.description && (
                        <p className="text-[11px] text-scurry-gray-muted truncate">
                          {resource.description}
                        </p>
                      )}
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-md text-[10px] font-semibold whitespace-nowrap ${
                        modeBgColors[config.mode] || modeBgColors.ai_decides
                      }`}
                    >
                      {modeLabels[config.mode] || modeLabels.ai_decides}
                    </span>
                    <ChevronRight
                      className={`h-3.5 w-3.5 text-scurry-gray-muted transition-transform ${
                        isExpanded ? "rotate-90" : ""
                      }`}
                    />
                  </button>

                  {/* Expanded: mode selector */}
                  {isExpanded && (
                    <div className="px-3 pb-3 pt-2 border-t border-scurry-gray-border bg-scurry-gray-light/50">
                      <p className="text-[11px] font-semibold text-scurry-latte mb-2">
                        How should this resource be used in this email?
                      </p>
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {(
                          [
                            { id: "ai_decides", label: "🤖 AI Decides" },
                            { id: "always", label: "📌 Always" },
                            { id: "custom_prompt", label: "💡 Custom" },
                            { id: "disabled", label: "⛔ Off" },
                          ] as const
                        ).map((mode) => {
                          const isActive = config.mode === mode.id;
                          return (
                            <button
                              key={mode.id}
                              type="button"
                              onClick={() =>
                                setResourceConfig((prev) => ({
                                  ...prev,
                                  [resource.id]: {
                                    ...prev[resource.id],
                                    mode: mode.id,
                                    customPrompt:
                                      prev[resource.id]?.customPrompt || "",
                                  },
                                }))
                              }
                              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                                isActive
                                  ? "border-scurry-orange bg-scurry-orange-light text-scurry-orange"
                                  : "border-scurry-gray-border bg-white text-scurry-latte hover:border-scurry-orange/30"
                              }`}
                            >
                              {mode.label}
                            </button>
                          );
                        })}
                      </div>

                      {/* Custom prompt field */}
                      {config.mode === "custom_prompt" && (
                        <div className="mt-2">
                          <label className="block text-[11px] font-semibold text-scurry-latte mb-1">
                            Custom instructions for this email:
                          </label>
                          <textarea
                            value={config.customPrompt}
                            onChange={(e) =>
                              setResourceConfig((prev) => ({
                                ...prev,
                                [resource.id]: {
                                  ...prev[resource.id],
                                  customPrompt: e.target.value,
                                },
                              }))
                            }
                            rows={2}
                            placeholder='e.g. Only use as closing CTA. Use "grab time" not "book a call".'
                            className="w-full px-3 py-2 border border-scurry-latte/20 rounded-lg text-xs resize-none focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                          />
                        </div>
                      )}

                      {/* AI context preview */}
                      {config.mode === "ai_decides" && resource.description && (
                        <div className="mt-2 p-2.5 bg-scurry-foam rounded-lg border border-scurry-yellow/20">
                          <p className="text-[10px] font-semibold text-scurry-latte mb-0.5">
                            AI will use this description to decide:
                          </p>
                          <p className="text-[11px] text-scurry-espresso italic leading-relaxed">
                            "{resource.description}"
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {activeResources.length > 0 && (
              <>
                <a
                  href="/resources"
                  className="inline-flex items-center gap-1 text-xs text-scurry-orange font-medium mt-1 hover:underline"
                >
                  Manage Resources <ExternalLink className="h-3 w-3" />
                </a>

                <div className="flex items-start gap-2 p-2.5 rounded-lg bg-scurry-blue-bg/50 mt-1">
                  <span className="text-xs mt-0.5">💡</span>
                  <p className="text-[11px] text-scurry-blue-text leading-relaxed">
                    "Always" resources are included regardless. "AI Decides" uses
                    each resource's description to judge relevance. "Custom" lets
                    you write per-email instructions. ~1 extra Acorn per email when
                    enabled.
                  </p>
                </div>
              </>
            )}
          </div>
        )}
        {/* ── Divider ── */}
        <div className="h-px bg-scurry-gray-border -mx-5 my-5" />

        {/* ── Fresh Check sub-section ── */}
        <div className="flex items-center gap-2 mb-3">
          <Activity className="h-4 w-4 text-scurry-orange" />
          <h4 className="text-[13px] font-bold text-scurry-espresso">
            Fresh Check
          </h4>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-scurry-foam text-scurry-latte">
            Workflow-level
          </span>
        </div>
        <p className="text-sm text-scurry-latte mb-4 leading-relaxed">
          Pre-send safety net. Watches replies, inbox activity, meetings,
          CRM changes, Pulse shifts, flagged notes, and DNC flips that
          happened after this email was drafted. Configured at the
          workflow level — open the workflow’s <strong>Context Settings</strong>
          panel to toggle each rule.
        </p>

        <div className="flex items-start gap-2 p-3 rounded-lg bg-scurry-blue-bg/50 mb-4">
          <span className="text-xs mt-0.5">💡</span>
          <p className="text-[11px] text-scurry-blue-text leading-relaxed">
            Fresh Check runs automatically before CRM and AI Filter checks.
            When any rule fires, Scurry picks an action (cancel, skip, or
            reschedule) instead of sending. The DNC rule is always on and
            cannot be turned off.
          </p>
        </div>

        {/* Migration banner — only if the admin set a legacy custom prompt */}
        {legacyTimelineCustomEnabled && (
          <div className="p-3 mb-3 rounded-lg border border-scurry-yellow/50 bg-scurry-yellow-light/30">
            <p className="text-xs font-semibold text-scurry-espresso">
              Legacy custom Timeline Check prompt detected
            </p>
            <p className="text-[11px] text-scurry-latte mt-1 leading-relaxed">
              Fresh Check no longer supports a free-form custom prompt on
              the Email component. Copy your custom prompt into a dedicated
              <strong> AI Filter</strong> component earlier in this workflow
              — it runs before Fresh Check and lets you combine arbitrary
              rules without losing the rule-matcher’s auditability.
            </p>
            {legacyTimelineCustomPrompt && (
              <pre className="text-[10px] text-scurry-gray-muted mt-2 whitespace-pre-wrap bg-white/70 rounded p-2 border border-scurry-gray-border max-h-40 overflow-y-auto">
                {legacyTimelineCustomPrompt.slice(0, 800)}
              </pre>
            )}
          </div>
        )}
        {/* ── Divider ── */}
        <div className="h-px bg-scurry-gray-border -mx-5 my-5" />

        {/* ── Pre-Send Check sub-section ── */}
        <p className="text-xs text-scurry-latte mb-4 leading-relaxed">
          Re-checks conditions right before sending. If a check fails, the email
          and remaining sequence emails are cancelled.
        </p>

        {/* ===== CRM Condition Sub-Section ===== */}
        <div className="mb-1">
          <button
            type="button"
            onClick={() => setCrmSubExpanded(!crmSubExpanded)}
            className="w-full flex items-center justify-between py-2.5 px-1 cursor-pointer select-none rounded-lg hover:bg-scurry-foam/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Shield className="h-[15px] w-[15px] text-scurry-orange" />
              <span className="text-[13px] font-bold text-scurry-espresso">
                CRM Condition
              </span>
              {crmEnabled && (
                <span className="w-[7px] h-[7px] rounded-full bg-green-500 shadow-[0_0_6px_rgba(76,175,80,0.35)]" />
              )}
            </div>
            {crmSubExpanded ? (
              <ChevronDown className="h-3 w-3 text-scurry-latte opacity-40" />
            ) : (
              <ChevronRight className="h-3 w-3 text-scurry-latte opacity-40" />
            )}
          </button>

          {crmSubExpanded && (
            <div className="flex flex-col gap-2.5 pb-4">
              {/* Data Source */}
              <div>
                <label className="block text-[11px] font-semibold text-scurry-latte mb-1">
                  Integration
                </label>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <select
                      className="w-full px-3 py-2.5 text-[13px] border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                      value={preSendConfig.dataSource}
                      onChange={(e) =>
                        setPreSendConfig((prev) => ({
                          ...prev,
                          dataSource: e.target.value,
                        }))
                      }
                    >
                      <option value="pipedrive">Pipedrive</option>
                      <option value="hubspot">HubSpot (Coming Soon)</option>
                      <option value="salesforce">
                        Salesforce (Coming Soon)
                      </option>
                    </select>
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">
                      &#9660;
                    </span>
                  </div>
                  <DataSourceTag source={preSendConfig.dataSource} />
                </div>
              </div>

              {/* Global Operator */}
              {preSendConfig.groups.length > 1 && (
                <div className="flex items-center gap-3 px-4 py-3 bg-scurry-foam/40 rounded-lg">
                  <span className="text-sm font-medium text-scurry-espresso">
                    Groups are combined with:
                  </span>
                  <OperatorToggle
                    value={preSendConfig.groupOperator}
                    onChange={togglePreSendGlobalOperator}
                    size="large"
                  />
                </div>
              )}

              {/* Condition Groups */}
              {preSendConfig.groups.length > 0 && (
                <div className="flex flex-col gap-0">
                  {preSendConfig.groups.map((group, groupIndex) => (
                    <React.Fragment key={group.id}>
                      {groupIndex > 0 && (
                        <div className="flex items-center justify-center py-2">
                          <div className="flex-1 h-0.5 bg-scurry-foam"></div>
                          <span className="px-4 py-1 bg-scurry-foam rounded-full text-xs font-bold text-scurry-orange mx-3">
                            {preSendConfig.groupOperator}
                          </span>
                          <div className="flex-1 h-0.5 bg-scurry-foam"></div>
                        </div>
                      )}

                      <div className="bg-scurry-foam/40 border border-scurry-foam rounded-xl p-4 transition-all hover:border-scurry-orange/40">
                        <div className="flex justify-between items-center mb-3">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-scurry-espresso">
                              Group {groupIndex + 1}
                            </span>
                            {group.conditions.length > 1 && (
                              <OperatorToggle
                                value={group.operator}
                                onChange={() =>
                                  togglePreSendGroupOperator(group.id)
                                }
                                size="small"
                              />
                            )}
                          </div>
                          {preSendConfig.groups.length > 1 && (
                            <button
                              type="button"
                              className="px-2 py-1 bg-transparent border border-red-200 rounded-md text-sm opacity-60 hover:opacity-100 transition-all"
                              onClick={() => removePreSendGroup(group.id)}
                            >
                              &#128465;
                            </button>
                          )}
                        </div>

                        {/* Conditions */}
                        <div className="flex flex-col gap-0">
                          {group.conditions.map((condition, condIndex) => (
                            <div
                              key={condition.id}
                              className="grid grid-cols-[1fr_160px_1fr_32px] gap-2 items-center py-2 relative"
                            >
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
                                  className={`w-full px-3 py-2.5 text-[13px] border border-scurry-latte/20 rounded-lg bg-white cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10 ${
                                    !condition.field
                                      ? "text-scurry-latte"
                                      : "text-scurry-espresso"
                                  }`}
                                  value={condition.field}
                                  onChange={(e) =>
                                    updatePreSendCondition(
                                      group.id,
                                      condition.id,
                                      "field",
                                      e.target.value,
                                    )
                                  }
                                >
                                  <option value="">Select field...</option>
                                  {preSendFieldDefs.map((f) => (
                                    <option key={f.value} value={f.value}>
                                      {f.icon} {f.label}
                                    </option>
                                  ))}
                                </select>
                                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">
                                  &#9660;
                                </span>
                              </div>

                              {/* Operator Select */}
                              <div className="relative min-w-0">
                                <select
                                  className="w-full px-3 py-2.5 text-[13px] border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                                  value={condition.operator}
                                  onChange={(e) =>
                                    updatePreSendCondition(
                                      group.id,
                                      condition.id,
                                      "operator",
                                      e.target.value,
                                    )
                                  }
                                >
                                  {OPERATOR_OPTIONS.map((op) => (
                                    <option key={op.value} value={op.value}>
                                      {op.symbol} {op.label}
                                    </option>
                                  ))}
                                </select>
                                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">
                                  &#9660;
                                </span>
                              </div>

                              {/* Value Input */}
                              <div className="min-w-0">
                                {condition.operator !== "is_empty" &&
                                condition.operator !== "is_not_empty" ? (
                                  renderValueInput(
                                    condition,
                                    group.id,
                                    preSendFieldDefs,
                                    updatePreSendCondition,
                                  )
                                ) : (
                                  <div className="px-3 py-2.5 bg-scurry-foam/50 rounded-lg text-[13px] text-scurry-latte text-center">
                                    No value needed
                                  </div>
                                )}
                              </div>

                              {/* Remove Condition */}
                              {group.conditions.length > 1 && (
                                <button
                                  type="button"
                                  className="w-7 h-7 flex items-center justify-center bg-transparent border border-scurry-gray-border rounded-md text-lg text-scurry-gray-muted hover:text-red-500 hover:border-red-300 transition-all"
                                  onClick={() =>
                                    removePreSendCondition(
                                      group.id,
                                      condition.id,
                                    )
                                  }
                                >
                                  &times;
                                </button>
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Add Condition Button */}
                        <button
                          type="button"
                          onClick={() => addPreSendCondition(group.id)}
                          className="mt-3 w-full py-2 border border-dashed border-scurry-gray-muted rounded-lg bg-transparent text-scurry-latte text-sm flex items-center justify-center gap-2 cursor-pointer transition-all hover:border-scurry-orange hover:text-scurry-orange hover:bg-scurry-orange/5"
                        >
                          <span className="text-lg leading-none">+</span>
                          Add Condition
                        </button>
                      </div>
                    </React.Fragment>
                  ))}
                </div>
              )}

              {/* Add Group Button */}
              <button
                type="button"
                onClick={addPreSendGroup}
                className="w-full py-2.5 border border-dashed border-scurry-gray-muted rounded-xl bg-transparent cursor-pointer transition-all hover:border-scurry-orange hover:bg-scurry-orange/5 flex items-center justify-center gap-2"
              >
                <span className="text-lg leading-none">+</span>
                <span className="text-sm font-medium text-scurry-latte">
                  {preSendConfig.groups.length === 0
                    ? "Add CRM Condition"
                    : "Add Condition Group"}
                </span>
              </button>

              {/* If check fails + Test */}
              <div className="flex items-end justify-between gap-3">
                <div className="flex-1">
                  <label className="block text-[11px] font-semibold text-scurry-latte mb-1">
                    If check fails
                  </label>
                  <div className="relative">
                    <select
                      className="w-full px-3 py-2.5 text-[13px] border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                      value={preSendConfig.crmIfFails}
                      onChange={(e) =>
                        setPreSendConfig((prev) => ({
                          ...prev,
                          crmIfFails: e.target.value as FailAction,
                        }))
                      }
                    >
                      <option value="cancel_sequence">
                        &#x1F6D1; Cancel email + remaining sequence
                      </option>
                      <option value="cancel_email">
                        &#x23F9; Cancel only this email
                      </option>
                      <option value="skip_proceed">
                        &#x23ED; Skip this email, continue sequence
                      </option>
                    </select>
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">
                      &#9660;
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {crmTestState === "loading" && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs font-medium">
                      <span className="animate-spin h-3 w-3 border-2 border-blue-400 border-t-transparent rounded-full" />
                      Testing...
                    </span>
                  )}
                  {crmTestState === "pass" && (
                    <span
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-green-50 text-green-700 rounded-lg text-xs font-semibold"
                      title={crmTestReason}
                    >
                      &#x2713; Passed
                    </span>
                  )}
                  {crmTestState === "fail" && (
                    <span
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-red-50 text-red-600 rounded-lg text-xs font-semibold"
                      title={crmTestReason}
                    >
                      &#x2717; Failed
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={handleCrmTest}
                    disabled={crmTestState === "loading" || !crmEnabled}
                    className="px-4 py-2.5 text-xs font-semibold rounded-lg bg-scurry-espresso text-white hover:bg-scurry-espresso/80 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                  >
                    Test
                  </button>
                </div>
              </div>

              {/* CRM Test Reason */}
              {crmTestState !== "idle" &&
                crmTestState !== "loading" &&
                crmTestReason && (
                  <div
                    className={`p-2 rounded-lg text-xs leading-relaxed ${crmTestState === "pass" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-600 border border-red-200"}`}
                  >
                    {crmTestReason}
                  </div>
                )}

              {/* CRM Summary */}
              {crmEnabled && (
                <div className="p-2.5 bg-green-50 border border-green-300 rounded-[10px] text-xs text-green-800 flex items-center gap-2 leading-relaxed">
                  <Shield className="h-3.5 w-3.5 flex-shrink-0" />
                  <span>
                    Before sending, will check{" "}
                    <strong>
                      {preSendConfig.groups.reduce(
                        (n, g) =>
                          n + g.conditions.filter((c) => c.field).length,
                        0,
                      )}{" "}
                      condition(s)
                    </strong>{" "}
                    across{" "}
                    <strong>{preSendConfig.groups.length} group(s)</strong> in{" "}
                    {preSendConfig.dataSource.charAt(0).toUpperCase() +
                      preSendConfig.dataSource.slice(1)}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ===== Divider ===== */}
        <div className="h-[1.5px] bg-gradient-to-r from-transparent via-scurry-foam to-transparent mx-0 my-1" />

        {/* ===== AI Filter Sub-Section ===== */}
        <div>
          <button
            type="button"
            onClick={() => {
              setAiSubExpanded(!aiSubExpanded);
              // Auto-enable when first expanding if not yet configured
              if (!aiSubExpanded && !preSendConfig.aiFilter) {
                setPreSendConfig((prev) => ({
                  ...prev,
                  aiFilter: {
                    enabled: true,
                    ai_prompt:
                      "Analyze the following information and determine if the client shows high buying intent. Return 'high intent', 'medium intent', or 'low intent' based on their engagement, questions, and interest level.",
                    condition_operator: "contains",
                    condition_value: "high intent",
                    case_sensitive: false,
                    if_fails: "cancel_sequence",
                  },
                }));
              }
            }}
            className="w-full flex items-center justify-between py-2.5 px-1 cursor-pointer select-none rounded-lg hover:bg-scurry-foam/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Brain className="h-[15px] w-[15px] text-scurry-orange" />
              <span className="text-[13px] font-bold text-scurry-espresso">
                AI Filter
              </span>
              {preSendConfig.aiFilter?.enabled && (
                <span className="w-[7px] h-[7px] rounded-full bg-green-500 shadow-[0_0_6px_rgba(76,175,80,0.35)]" />
              )}
            </div>
            {aiSubExpanded ? (
              <ChevronDown className="h-3 w-3 text-scurry-latte opacity-40" />
            ) : (
              <ChevronRight className="h-3 w-3 text-scurry-latte opacity-40" />
            )}
          </button>

          {aiSubExpanded && (
            <div className="flex flex-col gap-2.5 pb-2">
              {/* Enable toggle */}
              <div className="flex items-center justify-between px-1">
                <span className="text-xs text-scurry-latte">
                  Enable AI analysis before sending
                </span>
                <Switch
                  checked={preSendConfig.aiFilter?.enabled || false}
                  onCheckedChange={(checked) =>
                    setPreSendConfig((prev) => ({
                      ...prev,
                      aiFilter: {
                        enabled: checked,
                        ai_prompt:
                          prev.aiFilter?.ai_prompt ||
                          "Analyze the following information and determine if the client shows high buying intent. Return 'high intent', 'medium intent', or 'low intent' based on their engagement, questions, and interest level.",
                        condition_operator:
                          prev.aiFilter?.condition_operator || "contains",
                        condition_value:
                          prev.aiFilter?.condition_value || "high intent",
                        case_sensitive: prev.aiFilter?.case_sensitive || false,
                        if_fails: prev.aiFilter?.if_fails || "cancel_sequence",
                      },
                    }))
                  }
                />
              </div>

              {preSendConfig.aiFilter?.enabled && (
                <>
                  {/* AI Prompt */}
                  <div>
                    <label className="block text-[11px] font-semibold text-scurry-latte mb-1">
                      AI Analysis Prompt
                    </label>
                    <textarea
                      className="w-full min-h-[80px] p-3 text-xs border border-scurry-latte/20 rounded-lg font-mono resize-y leading-relaxed focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                      placeholder="Write a prompt that instructs the AI to analyze your data and return a specific response that can be evaluated."
                      value={preSendConfig.aiFilter.ai_prompt}
                      onChange={(e) =>
                        setPreSendConfig((prev) => ({
                          ...prev,
                          aiFilter: {
                            ...prev.aiFilter!,
                            ai_prompt: e.target.value,
                          },
                        }))
                      }
                    />
                    <p className="text-[11px] text-scurry-latte/70 mt-1">
                      <strong className="text-scurry-latte">Tip:</strong> For
                      numeric comparisons, ask the AI to return a number (e.g.,
                      &quot;Rate the urgency from 0-100&quot;).
                    </p>
                  </div>

                  {/* Proceed Condition */}
                  <div>
                    <label className="block text-[13px] font-bold text-scurry-espresso mb-2">
                      Proceed Condition
                    </label>
                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <label className="block text-[10px] font-semibold text-scurry-latte mb-1">
                          If AI response
                        </label>
                        <div className="relative">
                          <select
                            className="w-full px-3 py-2.5 text-[13px] border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                            value={preSendConfig.aiFilter.condition_operator}
                            onChange={(e) =>
                              setPreSendConfig((prev) => ({
                                ...prev,
                                aiFilter: {
                                  ...prev.aiFilter!,
                                  condition_operator: e.target.value,
                                },
                              }))
                            }
                          >
                            <option value="contains">Contains</option>
                            <option value="not_contains">
                              Does Not Contain
                            </option>
                            <option value="equals">Equals</option>
                            <option value="not_equals">Not Equals</option>
                            <option value="starts_with">Starts With</option>
                            <option value="ends_with">Ends With</option>
                            <option value="greater_than">
                              &gt; Greater Than
                            </option>
                            <option value="less_than">&lt; Less Than</option>
                            <option value="matches_regex">Matches Regex</option>
                            <option value="positive_sentiment">
                              Has Positive Sentiment
                            </option>
                            <option value="negative_sentiment">
                              Has Negative Sentiment
                            </option>
                            <option value="neutral_sentiment">
                              Has Neutral Sentiment
                            </option>
                          </select>
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">
                            &#9660;
                          </span>
                        </div>
                      </div>
                      <div>
                        <label className="block text-[10px] font-semibold text-scurry-latte mb-1">
                          Value to check
                        </label>
                        <Input
                          className="text-[13px]"
                          placeholder={
                            [
                              "positive_sentiment",
                              "negative_sentiment",
                              "neutral_sentiment",
                            ].includes(
                              preSendConfig.aiFilter.condition_operator,
                            )
                              ? "Not required for sentiment"
                              : "e.g. high intent"
                          }
                          value={preSendConfig.aiFilter.condition_value}
                          onChange={(e) =>
                            setPreSendConfig((prev) => ({
                              ...prev,
                              aiFilter: {
                                ...prev.aiFilter!,
                                condition_value: e.target.value,
                              },
                            }))
                          }
                          disabled={[
                            "positive_sentiment",
                            "negative_sentiment",
                            "neutral_sentiment",
                          ].includes(preSendConfig.aiFilter.condition_operator)}
                        />
                      </div>
                    </div>

                    {/* Case Sensitive */}
                    <label className="flex items-center gap-2 mt-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={preSendConfig.aiFilter.case_sensitive}
                        onChange={(e) =>
                          setPreSendConfig((prev) => ({
                            ...prev,
                            aiFilter: {
                              ...prev.aiFilter!,
                              case_sensitive: e.target.checked,
                            },
                          }))
                        }
                        className="w-[15px] h-[15px] accent-scurry-orange"
                      />
                      <span className="text-xs text-scurry-latte">
                        Case sensitive
                      </span>
                    </label>
                  </div>

                  {/* If check fails + Test */}
                  <div className="flex items-end justify-between gap-3">
                    <div className="flex-1">
                      <label className="block text-[11px] font-semibold text-scurry-latte mb-1">
                        If check fails
                      </label>
                      <div className="relative">
                        <select
                          className="w-full px-3 py-2.5 text-[13px] border border-scurry-latte/20 rounded-lg bg-white text-scurry-espresso cursor-pointer appearance-none transition-all focus:outline-none focus:border-scurry-orange focus:ring-2 focus:ring-scurry-orange/10"
                          value={preSendConfig.aiFilter.if_fails}
                          onChange={(e) =>
                            setPreSendConfig((prev) => ({
                              ...prev,
                              aiFilter: {
                                ...prev.aiFilter!,
                                if_fails: e.target.value as FailAction,
                              },
                            }))
                          }
                        >
                          <option value="cancel_sequence">
                            &#x1F6D1; Cancel email + remaining sequence
                          </option>
                          <option value="cancel_email">
                            &#x23F9; Cancel only this email
                          </option>
                          <option value="skip_proceed">
                            &#x23ED; Skip this email, continue sequence
                          </option>
                        </select>
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-scurry-latte pointer-events-none">
                          &#9660;
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {aiTestState === "loading" && (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-xs font-medium">
                          <span className="animate-spin h-3 w-3 border-2 border-blue-400 border-t-transparent rounded-full" />
                          Testing...
                        </span>
                      )}
                      {aiTestState === "pass" && (
                        <span
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-green-50 text-green-700 rounded-lg text-xs font-semibold"
                          title={aiTestReason}
                        >
                          &#x2713; Passed
                        </span>
                      )}
                      {aiTestState === "fail" && (
                        <span
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-red-50 text-red-600 rounded-lg text-xs font-semibold"
                          title={aiTestReason}
                        >
                          &#x2717; Failed
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={handleAiTest}
                        disabled={
                          aiTestState === "loading" ||
                          !preSendConfig.aiFilter?.enabled
                        }
                        className="px-4 py-2.5 text-xs font-semibold rounded-lg bg-scurry-espresso text-white hover:bg-scurry-espresso/80 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
                      >
                        Test
                      </button>
                    </div>
                  </div>

                  {/* AI Test Reason */}
                  {aiTestState !== "idle" &&
                    aiTestState !== "loading" &&
                    aiTestReason && (
                      <div
                        className={`p-2 rounded-lg text-xs leading-relaxed ${aiTestState === "pass" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-600 border border-red-200"}`}
                      >
                        {aiTestReason}
                      </div>
                    )}

                  {/* AI Summary */}
                  <div className="p-2.5 bg-green-50 border border-green-300 rounded-[10px] text-xs text-green-800 flex items-center gap-2 leading-relaxed">
                    <Brain className="h-3.5 w-3.5 flex-shrink-0" />
                    <span>
                      Before sending, AI will analyze the data and proceed if
                      response{" "}
                      <strong>
                        {preSendConfig.aiFilter.condition_operator.replace(
                          /_/g,
                          " ",
                        )}
                      </strong>{" "}
                      &quot;
                      <strong>{preSendConfig.aiFilter.condition_value}</strong>
                      &quot;
                    </span>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        {/* ===== Example Use Cases ===== */}
        <div className="mt-3 p-3 bg-scurry-foam rounded-[10px] border border-yellow-200/40 text-xs text-scurry-latte leading-relaxed">
          <p className="font-bold text-scurry-espresso text-[13px] mb-1">
            Example Use Cases:
          </p>
          <div className="flex flex-col gap-0.5">
            <span>
              <strong className="text-scurry-orange">Deal stage gate:</strong>{" "}
              Only send if deal is still in &quot;Discovery&quot;
            </span>
            <span>
              <strong className="text-scurry-orange">Lost deal block:</strong>{" "}
              Cancel sequence if deal moved to &quot;Lost&quot;
            </span>
            <span>
              <strong className="text-scurry-orange">AI sentiment:</strong> Only
              proceed if AI detects &quot;high intent&quot; in context
            </span>
            <span>
              <strong className="text-scurry-orange">Value threshold:</strong>{" "}
              Skip if AI rates urgency below 50
            </span>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  );
};

export default EmailConfig;
