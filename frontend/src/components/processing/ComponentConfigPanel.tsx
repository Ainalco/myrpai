import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle,
  Copy,
  Eye,
  EyeOff,
  Info,
  Link,
  Pencil,
  Save,
  Trash2
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import LoadingSpinner from "@/components/ui/loading-spinner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import VariableTextEditor from "@/components/ui/variable-text-editor";
import { Component, componentApi } from "@/lib/api";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  Copy as CopyIcon,
  Database,
  Edit as EditIcon,
  FileCode,
  FileText,
  Mail,
  MessageSquare,
  Settings,
  Shuffle,
  Sparkles,
  Zap,
} from "lucide-react";

// Icon mapping for component types (matches backend component.py icon values)
const COMPONENT_ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  'file': FileText,
  'document': FileText,
  'mail': Mail,
  'branch': Shuffle,
  'brain': MessageSquare,
  'external-link': Database,
  'filter': MessageSquare,
  'zap': Zap,
};
import ActionConfig from "./ActionConfig";
import AdvancedActionConfig from "./AdvancedActionConfig";
import AdvancedMatchingConfig from "./AdvancedMatchingConfig";
import AIFilterConfig from "./AIFilterConfig";
import ComponentTestUI from "./ComponentTestUI";
import ConditionalLogicConfig from "./ConditionalLogicConfig";
import EmailConfig from "./EmailConfig";
import ExtractionPointsConfig from "./ExtractionPointsConfig";
import InputSourcesConfig from "./InputSourcesConfig";

interface ComponentConfigPanelProps {
  workflowId: number;
  component: Component;
}

interface ConfigField {
  key: string;
  label: string;
  type:
    | "text"
    | "textarea"
    | "select"
    | "boolean"
    | "password"
    | "number"
    | "custom";
  description?: string;
  component?: string;
  defaultValue?: any;
  required?: boolean;
  options?: { value: string; label: string }[];
  placeholder?: string;
  validation?: {
    pattern?: string;
    min?: number;
    max?: number;
  };
}

const COMPONENT_CONFIG_SCHEMAS: Record<string, ConfigField[]> = {
  // input_sources now uses a custom component
  ai_filter: [
    {
      key: "analysis_model",
      label: "Analysis Model",
      type: "select",
      description: "AI model to use for sentiment analysis",
      required: true,
      options: [
        { value: "openai_gpt4", label: "OpenAI GPT-4" },
        { value: "anthropic_claude", label: "Anthropic Claude" },
        { value: "google_palm", label: "Google PaLM" },
        { value: "local_model", label: "Local Model" },
      ],
    },
    {
      key: "api_key",
      label: "API Key",
      type: "password",
      description: "API key for the selected sentiment analysis service",
      required: true,
    },
    {
      key: "analyze_emotions",
      label: "Analyze Emotions",
      type: "boolean",
      description: "Include detailed emotion analysis beyond basic sentiment",
    },
    {
      key: "context_window",
      label: "Context Window",
      type: "number",
      description: "Number of sentences to consider for context",
      validation: { min: 1, max: 10 },
      placeholder: "3",
    },
  ],
  action: [
    {
      key: "crm_system",
      label: "CRM System",
      type: "select",
      description: "Target CRM system for updates",
      required: true,
      options: [
        { value: "salesforce", label: "Salesforce" },
        { value: "hubspot", label: "HubSpot" },
        { value: "pipedrive", label: "Pipedrive" },
        { value: "zoho", label: "Zoho CRM" },
        { value: "custom_api", label: "Custom API" },
      ],
    },
    {
      key: "api_endpoint",
      label: "API Endpoint",
      type: "text",
      description: "CRM API endpoint URL",
      required: true,
      placeholder: "https://api.salesforce.com/v1/leads",
    },
    {
      key: "api_key",
      label: "API Key",
      type: "password",
      description: "Authentication key for CRM API",
      required: true,
    },
    {
      key: "update_fields",
      label: "Update Fields",
      type: "textarea",
      description: "JSON mapping of transcript data to CRM fields",
      placeholder:
        '{"lead_source": "call", "last_contact": "{{timestamp}}", "notes": "{{summary}}"}',
    },
    {
      key: "create_if_missing",
      label: "Create if Missing",
      type: "boolean",
      description: "Create new records if contact doesn't exist",
    },
  ],
  email: [
    {
      key: "prompt",
      label: "Email Content Prompt",
      type: "textarea",
      description:
        "AI prompt to generate email content. Use /VariableName to insert pipeline variables.",
      required: true,
      placeholder:
        "Write a professional follow-up email based on the meeting summary:\n/Summary\n\nInclude next steps: /Next Steps\nMention pain points: /Pain Points\n\nTone: Professional and friendly\nLength: 2-3 paragraphs",
    },
    {
      key: "send_timing",
      label: "Send Timing",
      type: "select",
      description: "When to send the email",
      required: true,
      options: [
        {
          value: "immediate",
          label: "Immediate - Send as soon as pipeline completes",
        },
        {
          value: "fixed_delay",
          label: "Fixed Delay - Wait specific time after trigger",
        },
      ],
    },
    {
      key: "delay_value",
      label: "Delay Time",
      type: "number",
      description: "Time to wait (only for Fixed Delay)",
      validation: { min: 1, max: 10080 },
      placeholder: "30",
    },
    {
      key: "delay_unit",
      label: "Delay Unit",
      type: "select",
      description: "Time unit for delay",
      options: [
        { value: "minutes", label: "Minutes" },
        { value: "hours", label: "Hours" },
        { value: "days", label: "Days" },
      ],
    },
    {
      key: "business_hours_only",
      label: "Business Hours Only",
      type: "boolean",
      description: "Send only during business hours (9am-5pm)",
    },
    {
      key: "avoid_weekends",
      label: "Avoid Weekends",
      type: "boolean",
      description: "Do not send emails on weekends",
    },
    {
      key: "skip_if_responded",
      label: "Skip if Already Responded",
      type: "boolean",
      description: "Do not send if recipient has already responded",
    },
    {
      key: "skip_if_meeting_scheduled",
      label: "Skip if Meeting Scheduled",
      type: "boolean",
      description: "Do not send if a meeting has been scheduled",
    },
    {
      key: "skip_if_deal_closed",
      label: "Skip if Deal Closed",
      type: "boolean",
      description: "Do not send if deal stage is Closed Won",
    },
    {
      key: "skip_if_bounced",
      label: "Skip if Previous Email Bounced",
      type: "boolean",
      description: "Do not send if previous email to this recipient bounced",
    },
    {
      key: "custom_skip_field",
      label: "Custom Skip Field",
      type: "text",
      description: "Custom field name to check for skip condition",
      placeholder: "e.g., do_not_contact",
    },
    {
      key: "custom_skip_value",
      label: "Custom Skip Value",
      type: "text",
      description: "Value that triggers skip when found in custom field",
      placeholder: "e.g., true",
    },
    {
      key: "smtp_server",
      label: "SMTP Server",
      type: "text",
      description: "SMTP server hostname",
      required: true,
      placeholder: "smtp.gmail.com",
    },
    {
      key: "smtp_port",
      label: "SMTP Port",
      type: "number",
      description: "SMTP server port",
      required: true,
      validation: { min: 1, max: 65535 },
      placeholder: "587",
    },
    {
      key: "username",
      label: "Email Username",
      type: "text",
      description: "SMTP authentication username",
      required: true,
      placeholder: "your-email@company.com",
    },
    {
      key: "password",
      label: "Email Password",
      type: "password",
      description: "SMTP authentication password",
      required: true,
    },
    {
      key: "use_tls",
      label: "Use TLS",
      type: "boolean",
      description: "Enable TLS encryption for email sending",
    },
  ],
  text_generation: [
    {
      key: "extraction_points",
      label: "Key Information Extraction Points",
      type: "custom",
      description:
        "Define what key information to extract from meeting transcripts using AI",
      component: "ExtractionPointsConfig",
      defaultValue: [
        {
          name: "Participants",
          description:
            "Extract all participants with their full names, companies, and roles. Identify team members vs clients.",
          required: true,
          type: "array",
        },
        {
          name: "Pain Points",
          description:
            "Identify and list all pain points, challenges, or problems mentioned during the call.",
          required: true,
          type: "array",
        },
        {
          name: "Budget",
          description:
            "Extract any budget information, price ranges, or financial constraints mentioned.",
          required: false,
          type: "string",
        },
        {
          name: "Timeline",
          description:
            "Identify implementation timeline, deadlines, or time-related requirements.",
          required: false,
          type: "string",
        },
        {
          name: "Next Steps",
          description:
            "Extract all agreed upon next steps, action items, and follow-up tasks.",
          required: true,
          type: "array",
        },
        {
          name: "Competitors",
          description:
            "Note any competitors or alternative solutions mentioned during the discussion.",
          required: false,
          type: "array",
        },
      ],
    },
    {
      key: "ai_prompt",
      label: "AI Prompt Configuration",
      type: "textarea",
      description: "Configure the AI prompt for extracting information",
      placeholder: "",
      required: false,
      defaultValue: `### Objective
Analyze the complete {{Full Transcript}} to extract and structure all relevant information for personalized follow-up email generation.

### Critical Participant Identification
**MANDATORY TEAM RECOGNITION:**
- **Joshua Murphy** = CRM Squirrel Founder (team member, NOT client)

### Information to Extract:
Based on the configured key information fields, extract the following:
{{keyInfoPrompts}}

### Output Format:
Return structured JSON with clear categorization of extracted information.`,
    },
  ],
  conditional_logic: [
    {
      key: "task_system",
      label: "Task Management System",
      type: "select",
      description: "Project management system for task creation",
      required: true,
      options: [
        { value: "asana", label: "Asana" },
        { value: "trello", label: "Trello" },
        { value: "monday", label: "Monday.com" },
        { value: "jira", label: "Jira" },
        { value: "todoist", label: "Todoist" },
      ],
    },
    {
      key: "api_token",
      label: "API Token",
      type: "password",
      description: "Authentication token for task management API",
      required: true,
    },
    {
      key: "project_id",
      label: "Project ID",
      type: "text",
      description: "Default project or workspace ID for tasks",
      required: true,
    },
    {
      key: "task_template",
      label: "Task Template",
      type: "textarea",
      description: "Template for task creation with placeholders",
      placeholder:
        "Follow up with {{customer_name}} regarding {{call_topic}}\n\nDue: {{due_date}}\nPriority: {{priority}}",
    },
    {
      key: "auto_assign",
      label: "Auto Assign Tasks",
      type: "boolean",
      description: "Automatically assign tasks based on call participants",
    },
  ],
};

const ComponentConfigPanel: React.FC<ComponentConfigPanelProps> = ({
  workflowId,
  component,
}) => {
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>(
    {}
  );
  const [webhookUrl, setWebhookUrl] = useState<string | null>(null);
  const [showWebhookSetup, setShowWebhookSetup] = useState(false);
  const [showAIPrompt, setShowAIPrompt] = useState(false);
  const [editingAIPrompt, setEditingAIPrompt] = useState(false);
  const [showKeyInfoExtraction, setShowKeyInfoExtraction] = useState(true);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState(component.name);
  const [isEditingDescription, setIsEditingDescription] = useState(false);
  const [editDescription, setEditDescription] = useState(component.description || "");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const descriptionInputRef = useRef<HTMLTextAreaElement>(null);
  const aiPromptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Fetch available variables from previous components for Text Generation
  const { data: availableVariables } = useQuery({
    queryKey: ["component-variables", component.id],
    queryFn: async () => {
      const response = await componentApi.getAvailableVariables(component.id);
      return response.data.available_variables;
    },
    enabled: component.type === "text_generation", // Only fetch for text generation components
  });

  // Fetch component types to get icon information
  const { data: componentTypesData } = useQuery({
    queryKey: ["component-types"],
    queryFn: () => componentApi.getTypes().then((res) => res.data),
    staleTime: 10 * 60 * 1000, // 10 minutes - types rarely change
  });

  // Get the icon for the current component type
  const getComponentIcon = () => {
    if (componentTypesData && componentTypesData[component.type]) {
      const iconName = componentTypesData[component.type].icon;
      return COMPONENT_ICON_MAP[iconName] || Settings;
    }
    return Settings;
  };
  const ComponentIcon = getComponentIcon();

  const configSchema = COMPONENT_CONFIG_SCHEMAS[component.type] || [];

  // Merge component configuration with schema defaults
  const getDefaultValues = () => {
    const schemaDefaults: Record<string, any> = {};
    configSchema.forEach((field) => {
      if (field.defaultValue !== undefined) {
        schemaDefaults[field.key] = field.defaultValue;
      }
    });
    return { ...schemaDefaults, ...component.configuration };
  };

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm({
    defaultValues: getDefaultValues(),
  });

  const updateConfigMutation = useMutation({
    mutationFn: (config: any) =>
      componentApi.updateConfig(component.id, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      // Dispatch success event for parent component
      const event = new CustomEvent("configuration-saved", {
        detail: { componentId: component.id, success: true },
      });
      window.dispatchEvent(event);
    },
    onError: () => {
      // Dispatch error event for parent component
      const event = new CustomEvent("configuration-saved", {
        detail: { componentId: component.id, success: false },
      });
      window.dispatchEvent(event);
    },
  });

  const updateNameMutation = useMutation({
    mutationFn: (newName: string) =>
      componentApi.update(workflowId, component.id, { name: newName }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      setIsEditingName(false);
      toast({
        title: "Success",
        description: "Component renamed successfully",
      });
    },
    onError: () => {
      setEditName(component.name);
      toast({
        title: "Error",
        description: "Failed to rename component",
        variant: "destructive",
      });
    },
  });

  const updateDescriptionMutation = useMutation({
    mutationFn: (newDescription: string) =>
      componentApi.update(workflowId, component.id, { description: newDescription }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      setIsEditingDescription(false);
      toast({
        title: "Success",
        description: "Component description updated successfully",
      });
    },
    onError: () => {
      setEditDescription(component.description || "");
      toast({
        title: "Error",
        description: "Failed to update description",
        variant: "destructive",
      });
    },
  });

  const deleteComponentMutation = useMutation({
    mutationFn: () => componentApi.delete(workflowId, component.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      queryClient.invalidateQueries({ queryKey: ["connections", workflowId] });
      toast({
        title: "Success",
        description: "Component deleted successfully",
      });
    },
    onError: () => {
      toast({
        title: "Error",
        description: "Failed to delete component",
        variant: "destructive",
      });
    },
  });

  const watchedValues = watch();
  const sourceType = watchedValues["source_type"];

  // Handle textarea input to detect {{ for variable suggestions (Text Generation)
  const handleAIPromptInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = e.target;
    const value = textarea.value;
    const cursorPos = textarea.selectionStart;

    // Check if user just typed {{
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastTwoChars = textBeforeCursor.slice(-2);

    if (lastTwoChars === "{{") {
      setShowSuggestions(true);
    } else if (!textBeforeCursor.endsWith("{")) {
      setShowSuggestions(false);
    }
  };

  // Insert variable at cursor position (Text Generation)
  const insertAIPromptVariable = (variableValue: string) => {
    if (!aiPromptTextareaRef.current) return;

    const textarea = aiPromptTextareaRef.current;
    const currentValue = watchedValues["ai_prompt"] || "";
    const cursorPos = textarea.selectionStart;

    // Find the {{ before cursor
    const textBeforeCursor = currentValue.substring(0, cursorPos);
    const lastBraceIndex = textBeforeCursor.lastIndexOf("{{");

    if (lastBraceIndex !== -1) {
      // Replace {{ with {{VariableName}}
      const newValue =
        currentValue.substring(0, lastBraceIndex) +
        `{{${variableValue}}}` +
        currentValue.substring(cursorPos);

      setValue("ai_prompt", newValue);
      setShowSuggestions(false);

      // Set cursor position after inserted variable
      setTimeout(() => {
        const newCursorPos = lastBraceIndex + variableValue.length + 4; // 4 for {{}}
        textarea.selectionStart = newCursorPos;
        textarea.selectionEnd = newCursorPos;
        textarea.focus();
      }, 0);
    }
  };

  // Close suggestions when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setShowSuggestions(false);
    if (showSuggestions) {
      document.addEventListener("click", handleClickOutside);
      return () => document.removeEventListener("click", handleClickOutside);
    }
  }, [showSuggestions]);

  // Render AI Prompt with variable highlighting
  const renderAIPromptWithVariables = (text: string) => {
    if (!text) return <span className="text-scurry-latte italic">No prompt configured yet.</span>;

    const parts = text.split(/(\{\{[^}]+\}\})/g);
    return (
      <div className="text-sm text-scurry-espresso whitespace-pre-wrap font-mono leading-relaxed">
        {parts.map((part, i) => {
          if (part.match(/\{\{[^}]+\}\}/)) {
            const varName = part.replace(/\{\{|\}\}/g, "").trim();
            return (
              <span
                key={i}
                className="inline-flex items-center gap-1 mx-1 my-0.5 px-2.5 py-1 bg-gradient-to-r from-scurry-orange to-scurry-orange-hover text-white rounded-md shadow-sm font-semibold text-xs hover:from-scurry-orange-hover hover:to-scurry-orange transition-all"
                title={`Variable: ${varName}`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                {varName}
              </span>
            );
          }
          return (
            <span key={i} className="text-scurry-espresso">
              {part}
            </span>
          );
        })}
      </div>
    );
  };

  // Check for existing webhook when component is input_sources
  const { data: existingWebhook, refetch: refetchWebhook } = useQuery({
    queryKey: ["webhook", component.id],
    queryFn: async () => {
      if (component.type !== "input_sources") {
        return null;
      }
      const API_BASE_URL =
        import.meta.env.VITE_API_URL || "http://localhost:9000";
      const response = await fetch(`${API_BASE_URL}/webhooks/${workflowId}`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
      });
      if (!response.ok) return null;
      const webhooks = await response.json();
      return webhooks.find((w: any) => w.component_id === component.id) || null;
    },
    enabled: component.type === "input_sources",
  });

  useEffect(() => {
    // Reset form with merged defaults and configuration
    const defaultValues = getDefaultValues();
    Object.entries(defaultValues).forEach(([key, value]) => {
      setValue(key, value);
    });
  }, [component.configuration, setValue]);

  useEffect(() => {
    if (existingWebhook?.webhook_url) {
      setWebhookUrl(existingWebhook.webhook_url);
    }
  }, [existingWebhook]);

  useEffect(() => {
    setEditName(component.name);
    setEditDescription(component.description || "");
  }, [component.name, component.description]);

  // Listen for save-configuration event from parent
  useEffect(() => {
    const handleSaveEvent = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.componentId === component.id) {
        handleSubmit(onSubmit)();
      }
    };

    window.addEventListener("save-configuration", handleSaveEvent);
    return () => {
      window.removeEventListener("save-configuration", handleSaveEvent);
    };
  }, [component.id]);

  // Automatically create webhook when Fireflies is selected and saved
  useEffect(() => {
    const createWebhookIfNeeded = async () => {
      if (
        component.type === "input_sources" &&
        sourceType === "fireflies_webhook" &&
        !webhookUrl &&
        !existingWebhook &&
        !createWebhookMutation.isPending
      ) {
        // Auto-create webhook with default values
        const webhookData = {
          webhook_name:
            watchedValues["webhook_name"] || "Fireflies Integration",
          webhook_description:
            watchedValues["webhook_description"] ||
            "Automatically created webhook for Fireflies.ai",
        };
        await createWebhookMutation.mutateAsync(webhookData);
      }
    };

    if (sourceType === "fireflies_webhook") {
      createWebhookIfNeeded();
    }
  }, [sourceType, component.type, webhookUrl, existingWebhook]);

  const createWebhookMutation = useMutation({
    mutationFn: async (data: any) => {
      const API_BASE_URL =
        import.meta.env.VITE_API_URL || "http://localhost:9000";
      const response = await fetch(`${API_BASE_URL}/webhooks/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`,
        },
        body: JSON.stringify({
          workflow_id: workflowId,
          component_id: component.id,
          name: data.webhook_name || "Fireflies Webhook",
          description: data.webhook_description,
        }),
      });
      if (!response.ok) throw new Error("Failed to create webhook");
      return response.json();
    },
    onSuccess: (data) => {
      setWebhookUrl(data.webhook_url);
      setShowWebhookSetup(true);
      queryClient.invalidateQueries({ queryKey: ["webhooks", workflowId] });
    },
  });

  const onSubmit = async (data: any) => {
    // First save the configuration
    await updateConfigMutation.mutateAsync(data);

    // If this is a Fireflies webhook source and no webhook exists, create one
    if (
      component.type === "input_sources" &&
      data.source_type === "fireflies_webhook" &&
      !webhookUrl
    ) {
      await createWebhookMutation.mutateAsync(data);
    }
  };

  const copyToClipboard = () => {
    if (webhookUrl) {
      navigator.clipboard.writeText(webhookUrl);
    }
  };

  const togglePasswordVisibility = (fieldKey: string) => {
    setShowPasswords((prev) => ({
      ...prev,
      [fieldKey]: !prev[fieldKey],
    }));
  };

  const handleRenameClick = () => {
    setIsEditingName(true);
    setTimeout(() => nameInputRef.current?.focus(), 0);
  };

  const handleSaveRename = () => {
    if (editName.trim() && editName !== component.name) {
      updateNameMutation.mutate(editName.trim());
    } else {
      setIsEditingName(false);
      setEditName(component.name);
    }
  };

  const handleCancelRename = () => {
    setIsEditingName(false);
    setEditName(component.name);
  };

  const handleNameKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSaveRename();
    } else if (e.key === "Escape") {
      handleCancelRename();
    }
  };

  const handleDescriptionClick = () => {
    setIsEditingDescription(true);
    setTimeout(() => descriptionInputRef.current?.focus(), 0);
  };

  const handleSaveDescription = () => {
    const trimmedDescription = editDescription.trim();
    if (trimmedDescription !== (component.description || "")) {
      updateDescriptionMutation.mutate(trimmedDescription);
    } else {
      setIsEditingDescription(false);
      setEditDescription(component.description || "");
    }
  };

  const handleCancelDescription = () => {
    setIsEditingDescription(false);
    setEditDescription(component.description || "");
  };

  const handleDescriptionKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSaveDescription();
    } else if (e.key === "Escape") {
      handleCancelDescription();
    }
  };

  const handleDeleteComponent = () => {
    if (
      confirm(
        `Are you sure you want to delete "${component.name}"? This action cannot be undone.`
      )
    ) {
      deleteComponentMutation.mutate();
    }
  };

  const hasRequiredFields =
    configSchema.filter((field) => field.required).length > 0;
  const isConfigured = configSchema
    .filter((field) => field.required)
    .every(
      (field) =>
        component.configuration?.[field.key] || watchedValues[field.key],
    );

  return (
    <div className="h-full flex flex-col bg-scurry-gray-light">
      {/* Header */}
      <div className="p-3 sm:p-4 border-b border-scurry-gray-border/50 bg-gradient-to-r from-scurry-foam/30 to-white">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            {isEditingName ? (
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-scurry-orange/10 flex items-center justify-center flex-shrink-0">
                  <ComponentIcon className="h-5 w-5 text-scurry-orange" />
                </div>
                <input
                  ref={nameInputRef}
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={handleNameKeyDown}
                  onBlur={handleSaveRename}
                  className="text-xl sm:text-2xl font-display font-bold text-scurry-espresso border border-scurry-orange rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-scurry-orange"
                />
              </div>
            ) : (
              <div className="flex items-center gap-2 group">
                <div className="w-8 h-8 rounded-lg bg-scurry-orange/10 flex items-center justify-center flex-shrink-0">
                  <ComponentIcon className="h-5 w-5 text-scurry-orange" />
                </div>
                <h2 className="text-xl sm:text-2xl font-display font-bold text-scurry-espresso">
                  {component.name}
                </h2>
                {component.type !== "input_sources" && (
                  <button
                    onClick={handleRenameClick}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-scurry-foam rounded"
                    title="Rename component"
                  >
                    <Pencil className="h-4 w-4 text-scurry-latte" />
                  </button>
                )}
              </div>
            )}
            {isEditingDescription ? (
              <div className="mt-1">
                <textarea
                  ref={descriptionInputRef}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  onKeyDown={handleDescriptionKeyDown}
                  onBlur={handleSaveDescription}
                  placeholder="Add a description to clarify what this component does..."
                  className="text-sm text-scurry-latte border border-scurry-orange rounded-lg px-2 py-1 w-full focus:outline-none focus:ring-2 focus:ring-scurry-orange resize-none"
                  rows={2}
                  maxLength={300}
                />
                <div className="text-xs text-scurry-latte/75 mt-0.5">
                  {editDescription.length}/300 characters • Press Enter to save, Shift+Enter for new line, Esc to cancel
                </div>
              </div>
            ) : (
              <div className="group/desc mt-1 flex items-start">
                <p className="text-sm text-scurry-latte">
                  {component.description || (
                    <span className="text-scurry-latte/75 italic">
                      Click to add a description
                    </span>
                  )}
                </p>
                <button
                  onClick={handleDescriptionClick}
                  className="opacity-0 group-hover/desc:opacity-100 transition-opacity p-1 hover:bg-scurry-foam rounded flex-shrink-0 ml-1"
                  title="Edit description"
                >
                  <Pencil className="h-3 w-3 text-scurry-latte" />
                </button>
              </div>
            )}
          </div>

          <div className="flex items-center space-x-3">
            {isConfigured ? (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-scurry-green-light rounded-full text-sm font-semibold text-scurry-green">
                <CheckCircle className="h-4 w-4" />
                <span>Configured</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 px-3 py-1.5 bg-scurry-orange-light rounded-full text-sm font-semibold text-scurry-orange">
                <AlertCircle className="h-4 w-4" />
                <span>Needs Setup</span>
              </div>
            )}

            {component.type !== "input_sources" && (
              <Button
                onClick={handleDeleteComponent}
                disabled={deleteComponentMutation.isPending}
                className="bg-scurry-red-light text-scurry-red hover:bg-scurry-red/10 border-none font-semibold"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Configuration Form */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-4">
        {/* Special handling for input_sources, email, conditional_logic, ai_filter, action, and company_name_matcher components */}
        {component.type === "input_sources" ? (
          <InputSourcesConfig workflowId={workflowId} component={component} />
        ) : component.type === "email" ? (
          <EmailConfig workflowId={workflowId} component={component} />
        ) : component.type === "conditional_logic" ? (
          <ConditionalLogicConfig
            workflowId={workflowId}
            component={component}
          />
        ) : component.type === "ai_filter" ? (
          <AIFilterConfig workflowId={workflowId} component={component} />
        ) : component.type === "action" ? (
          <ActionConfig workflowId={workflowId} component={component} />
        ) : component.type === "company_name_matcher" ? (
          <AdvancedMatchingConfig workflowId={workflowId} component={component} />
        ) : component.type === "advanced_action" ? (
          <AdvancedActionConfig workflowId={workflowId} component={component} />
        ) : configSchema.length === 0 ? (
          <div className="text-center py-8">
            <Info className="h-10 w-10 text-scurry-gray-muted mx-auto mb-3" />
            <h3 className="text-base sm:text-lg font-medium text-scurry-espresso mb-2">
              No Configuration Required
            </h3>
            <p className="text-sm text-scurry-latte">
              This component works out of the box with default settings.
            </p>
          </div>
        ) : (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="space-y-3 sm:space-y-4"
          >
            
            {/* Text Generation Info Bar */}
            {component.type === "text_generation" && (
              <div className="flex items-center gap-2 p-3 sm:p-4 bg-scurry-foam rounded-xl text-sm text-scurry-latte">
                <Sparkles className="h-4 w-4 text-scurry-orange flex-shrink-0" />
                <span>Generate summaries, subject lines, or any text from your transcripts! 🎯</span>
              </div>
            )}

            {/* Configuration Fields */}
            <div className="space-y-3 sm:space-y-4">
              {configSchema.map((field) => {
                // Hide webhook-specific fields if not using Fireflies webhook
                if (component.type === "input_sources") {
                  if (
                    (field.key === "webhook_name" ||
                      field.key === "webhook_description") &&
                    sourceType !== "fireflies_webhook"
                  ) {
                    return null;
                  }
                }

                return (
                  <div key={field.key} className="space-y-2">
                    {/* Skip label for custom components and ai_prompt as they have their own headers */}
                    {field.type !== "custom" && field.key !== "ai_prompt" && (
                      <Label
                        htmlFor={field.key}
                        className="text-sm font-medium text-scurry-espresso"
                      >
                        {field.label}
                        {field.required && (
                          <span className="text-scurry-red ml-1">*</span>
                        )}
                      </Label>
                    )}

                    {field.type === "text" && (
                      <Input
                        id={field.key}
                        placeholder={field.placeholder}
                        {...register(field.key, { required: field.required })}
                        className={errors[field.key] ? "border-scurry-red/50" : ""}
                      />
                    )}

                    {field.type === "password" && (
                      <div className="relative">
                        <Input
                          id={field.key}
                          type={showPasswords[field.key] ? "text" : "password"}
                          placeholder={field.placeholder}
                          {...register(field.key, { required: field.required })}
                          className={errors[field.key] ? "border-scurry-red/50" : ""}
                        />
                        <button
                          type="button"
                          onClick={() => togglePasswordVisibility(field.key)}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-scurry-gray-muted hover:text-scurry-latte"
                        >
                          {showPasswords[field.key] ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    )}

                    {field.type === "number" && (
                      <Input
                        id={field.key}
                        type="number"
                        placeholder={field.placeholder}
                        min={field.validation?.min}
                        max={field.validation?.max}
                        {...register(field.key, {
                          required: field.required,
                          min: field.validation?.min,
                          max: field.validation?.max,
                          valueAsNumber: true,
                        })}
                        className={errors[field.key] ? "border-scurry-red/50" : ""}
                      />
                    )}

                    {field.type === "textarea" &&
                    field.key === "ai_prompt" &&
                    component.type === "text_generation" ? (
                      <Card className="border-scurry-foam">
                        <Collapsible
                          open={showAIPrompt}
                          onOpenChange={setShowAIPrompt}
                        >
                          <CollapsibleTrigger asChild>
                            <CardHeader className="cursor-pointer hover:bg-scurry-foam/50 transition-colors">
                              <div className="flex items-center justify-between">
                                <CardTitle className="text-base font-semibold flex items-center text-scurry-espresso">
                                  <FileCode className="h-5 w-5 mr-2 text-scurry-orange" />
                                  AI Prompt Configuration
                                </CardTitle>
                                {showAIPrompt ? (
                                  <ChevronDown className="h-5 w-5 text-scurry-latte" />
                                ) : (
                                  <ChevronRight className="h-5 w-5 text-scurry-latte" />
                                )}
                              </div>
                            </CardHeader>
                          </CollapsibleTrigger>
                          <CollapsibleContent>
                            <CardContent>
                              <div className="space-y-4">
                                <div className="flex items-center justify-between p-3 bg-scurry-foam/50 rounded-lg border border-scurry-foam">
                                  <div className="flex items-center space-x-2">
                                    <Brain className="h-4 w-4 text-scurry-orange" />
                                    <span className="text-sm font-medium text-scurry-espresso">Powered by AI magic! ✨</span>
                                  </div>
                                  <div className="flex items-center space-x-2">
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      className="border-scurry-latte/25 text-scurry-espresso hover:bg-scurry-orange/10 hover:text-scurry-orange hover:border-scurry-orange/30"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        setEditingAIPrompt(true);
                                        setTimeout(() => {
                                          document
                                            .getElementById("ai_prompt")
                                            ?.focus();
                                        }, 100);
                                      }}
                                    >
                                      <EditIcon className="h-4 w-4 mr-1" />
                                      Edit
                                    </Button>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      className="border-scurry-latte/25 text-scurry-espresso hover:bg-scurry-orange/10 hover:text-scurry-orange hover:border-scurry-orange/30"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        const promptValue =
                                          watchedValues["ai_prompt"] ||
                                          field.defaultValue ||
                                          "";
                                        navigator.clipboard.writeText(
                                          promptValue
                                        );
                                      }}
                                    >
                                      <CopyIcon className="h-4 w-4 mr-1" />
                                      Copy
                                    </Button>
                                  </div>
                                </div>
                                {editingAIPrompt ? (
                                  <div className="space-y-2 relative">
                                    <Textarea
                                      id="ai_prompt"
                                      {...register(field.key, {
                                        required: field.required,
                                        onChange: handleAIPromptInput,
                                      })}
                                      ref={(e) => {
                                        register(field.key).ref(e);
                                        aiPromptTextareaRef.current = e;
                                      }}
                                      placeholder={field.placeholder}
                                      rows={12}
                                      className={`font-mono text-sm ${
                                        errors[field.key]
                                          ? "border-scurry-red/50"
                                          : ""
                                      }`}
                                      onBlur={() => setEditingAIPrompt(false)}
                                    />

                                    {/* Variable Suggestions Dropdown */}
                                    {showSuggestions &&
                                      availableVariables &&
                                      availableVariables.length > 0 && (
                                        <div
                                          className="absolute z-50 mt-1 bg-white border border-scurry-foam rounded-lg shadow-lg max-h-60 overflow-y-auto"
                                          onMouseDown={(e) => {
                                            // Prevent blur event on textarea when clicking suggestions
                                            e.preventDefault();
                                          }}
                                        >
                                          <div className="p-2 border-b border-scurry-foam bg-scurry-foam/50">
                                            <div className="flex items-center gap-2 text-xs text-scurry-espresso font-medium">
                                              <Sparkles className="h-3 w-3 text-scurry-orange" />
                                              <span>Available Variables</span>
                                            </div>
                                          </div>
                                          <div className="p-1">
                                            {availableVariables.map(
                                              (variable, index) => (
                                                <button
                                                  key={index}
                                                  type="button"
                                                  onClick={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                    insertAIPromptVariable(
                                                      variable.value
                                                    );
                                                  }}
                                                  className="w-full text-left px-3 py-2 hover:bg-scurry-orange/10 rounded flex items-center gap-2 group"
                                                >
                                                  <Sparkles className="h-4 w-4 text-scurry-orange" />
                                                  <div className="flex-1">
                                                    <div className="text-sm font-medium text-scurry-espresso">
                                                      {variable.value}
                                                    </div>
                                                    {variable.label && (
                                                      <div className="text-xs text-scurry-latte">
                                                        {variable.label}
                                                      </div>
                                                    )}
                                                  </div>
                                                  <div className="text-xs text-scurry-orange opacity-0 group-hover:opacity-100">
                                                    Click to insert
                                                  </div>
                                                </button>
                                              )
                                            )}
                                          </div>
                                        </div>
                                      )}

                                    <div className="flex items-start justify-between gap-2">
                                      <p className="text-xs text-scurry-latte">
                                        Type{" "}
                                        <code className="bg-scurry-foam px-1 rounded text-scurry-espresso">
                                          {"{{"}
                                        </code>{" "}
                                        to see available variables from previous
                                        components
                                      </p>
                                      {availableVariables &&
                                        availableVariables.length > 0 && (
                                          <div className="text-xs text-scurry-orange flex items-center gap-1">
                                            <Sparkles className="h-3 w-3" />
                                            {availableVariables.length} variables
                                            available
                                          </div>
                                        )}
                                    </div>

                                    <div className="flex justify-end space-x-2">
                                      <Button
                                        type="button"
                                        variant="outline"
                                        size="sm"
                                        onClick={() =>
                                          setEditingAIPrompt(false)
                                        }
                                      >
                                        Done
                                      </Button>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="bg-scurry-foam/30 rounded-lg p-4 border border-scurry-foam">
                                    {renderAIPromptWithVariables(
                                      watchedValues["ai_prompt"] ||
                                        field.defaultValue ||
                                        ""
                                    )}
                                  </div>
                                )}
                              </div>
                            </CardContent>
                          </CollapsibleContent>
                        </Collapsible>
                      </Card>
                    ) : field.type === "textarea" ? (
                      <VariableTextEditor
                        value={watchedValues[field.key] || ""}
                        onChange={(value) => setValue(field.key, value)}
                        placeholder={field.placeholder}
                        workflowId={workflowId}
                        componentId={component.id}
                        rows={4}
                        className={errors[field.key] ? "border-scurry-red/50" : ""}
                        previewVariables={[]}
                      />
                    ) : null}

                    {field.type === "select" && (
                      <Select
                        onValueChange={(value) => setValue(field.key, value)}
                        value={watchedValues[field.key] || ""}
                      >
                        <SelectTrigger
                          className={errors[field.key] ? "border-scurry-red/50" : ""}
                        >
                          <SelectValue
                            placeholder={`Select ${field.label.toLowerCase()}`}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          {field.options?.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}

                    {field.type === "boolean" && (
                      <div className="flex items-center space-x-2">
                        <Switch
                          id={field.key}
                          checked={watchedValues[field.key] || false}
                          onCheckedChange={(checked) =>
                            setValue(field.key, checked)
                          }
                        />
                        <Label
                          htmlFor={field.key}
                          className="text-sm text-scurry-latte"
                        >
                          Enable this option
                        </Label>
                      </div>
                    )}

                    {field.type === "custom" &&
                      field.component === "ExtractionPointsConfig" && (
                        <Card className="border-scurry-foam">
                          <Collapsible
                            open={showKeyInfoExtraction}
                            onOpenChange={setShowKeyInfoExtraction}
                          >
                            <CollapsibleTrigger asChild>
                              <CardHeader className="cursor-pointer hover:bg-scurry-foam/50 transition-colors">
                                <div className="flex items-center justify-between">
                                  <CardTitle className="text-base font-semibold flex items-center text-scurry-espresso">
                                    <span className="text-2xl mr-2">🥜</span>
                                    Key Information Extraction
                                  </CardTitle>
                                  {showKeyInfoExtraction ? (
                                    <ChevronDown className="h-5 w-5 text-scurry-latte" />
                                  ) : (
                                    <ChevronRight className="h-5 w-5 text-scurry-latte" />
                                  )}
                                </div>
                              </CardHeader>
                            </CollapsibleTrigger>
                            <CollapsibleContent>
                              <CardContent>
                                <ExtractionPointsConfig
                                  value={
                                    watchedValues[field.key] ||
                                    field.defaultValue ||
                                    []
                                  }
                                  onChange={(value) =>
                                    setValue(field.key, value)
                                  }
                                  error={
                                    errors[field.key]
                                      ? "This field is required"
                                      : undefined
                                  }
                                />
                              </CardContent>
                            </CollapsibleContent>
                          </Collapsible>
                        </Card>
                      )}

                    {/* Skip description for custom components and ai_prompt as they handle their own */}
                    {field.type !== "custom" &&
                      field.key !== "ai_prompt" &&
                      field.description && (
                        <p className="text-xs text-scurry-latte">
                          {field.description}
                        </p>
                      )}

                    {errors[field.key] && (
                      <p className="text-xs text-scurry-red">
                        This field is required
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Webhook URL Display for Fireflies - Show immediately when Fireflies is selected */}
            {component.type === "input_sources" &&
              sourceType === "fireflies_webhook" && (
                <Card className="mt-6">
                  <CardHeader>
                    <CardTitle className="text-sm font-medium flex items-center">
                      <Link className="h-4 w-4 mr-2" />
                      Webhook URL
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {webhookUrl ? (
                        <div className="bg-scurry-foam p-3 rounded-lg">
                          <p className="text-xs text-scurry-latte mb-2">
                            Add this URL to your Fireflies.ai webhook settings:
                          </p>
                          <div className="flex items-center space-x-2">
                            <code className="flex-1 p-2 bg-white border border-scurry-gray-border rounded text-xs break-all">
                              {webhookUrl}
                            </code>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={copyToClipboard}
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="bg-scurry-orange-light p-3 rounded-lg">
                          <p className="text-xs text-scurry-orange">
                            Save the configuration to generate your webhook URL
                          </p>
                        </div>
                      )}
                      <div className="text-xs text-scurry-latte">
                        <p className="font-medium mb-1 text-scurry-espresso">Setup Instructions:</p>
                        <ol className="list-decimal list-inside space-y-1">
                          <li>Go to your Fireflies.ai dashboard</li>
                          <li>Navigate to Integrations → Webhooks</li>
                          <li>Click "Add Webhook"</li>
                          <li>Paste the URL above</li>
                          <li>
                            Select the events you want to trigger (e.g.,
                            "Meeting Completed")
                          </li>
                          <li>Save the webhook configuration</li>
                        </ol>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

            {/* Save Button */}
            <div className="pt-3 sm:pt-4 border-t border-scurry-gray-border/50">
              <Button
                type="submit"
                disabled={
                  updateConfigMutation.isPending ||
                  createWebhookMutation.isPending
                }
                className="w-full bg-gradient-to-br from-scurry-orange to-scurry-orange-hover hover:from-scurry-orange-hover hover:to-scurry-orange-hover text-white font-semibold rounded-lg shadow-lg shadow-scurry-orange/25"
              >
                {updateConfigMutation.isPending ? (
                  <div className="flex items-center">
                    <LoadingSpinner size="sm" className="mr-2" />
                    Saving Configuration...
                  </div>
                ) : (
                  <div className="flex items-center">
                    <Save className="h-4 w-4 mr-2" />
                    Save Configuration
                  </div>
                )}
              </Button>
            </div>
          </form>
        )}

        {/* Test UI - Show for all component types */}
        <ComponentTestUI
          key={component.id}
          workflowId={workflowId}
          componentId={component.id}
          componentType={component.type}
        />
      </div>
    </div>
  );
};

export default ComponentConfigPanel;
