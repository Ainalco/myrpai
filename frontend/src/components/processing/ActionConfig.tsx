import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Database, Plus, RefreshCw, Trash2 } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

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
import { Component, componentApi } from "@/lib/api";
import { ChevronDown, ChevronRight } from "lucide-react";
import WebhookConfig from "./WebhookConfig";

interface ActionConfigProps {
  workflowId: number;
  component: Component;
}

interface FieldMapping {
  id: string;
  fieldName: string;
  sourceField: string;
}

interface CustomFieldMapping {
  id: string;
  crmField: string;
  sourceField: string;
}

interface ActionConfigData {
  // system: 'pipedrive' | 'hubspot' | 'salesforce' | 'custom_webhook'
  system: "pipedrive";
  action: "create_activity" | "update_deal" | "add_note";
  standard_fields: FieldMapping[];
  custom_field_mappings: CustomFieldMapping[];
}

const SYSTEMS = [
  { value: "pipedrive", label: "Pipedrive CRM" },
  { value: "custom_webhook", label: "Custom Webhook" },
  // { value: "hubspot", label: "HubSpot" },
  // { value: "salesforce", label: "Salesforce" },
];

const ACTIONS = {
  pipedrive: [
    { value: "create_activity", label: "Create Activity" },
    { value: "update_deal", label: "Update Deal" },
    { value: "add_note", label: "Add Note" },
  ],
  hubspot: [
    { value: "create_activity", label: "Create Activity" },
    { value: "update_deal", label: "Update Deal" },
    { value: "add_note", label: "Add Note" },
  ],
  salesforce: [
    { value: "create_activity", label: "Create Activity" },
    { value: "update_deal", label: "Update Opportunity" },
    { value: "add_note", label: "Add Note" },
  ],
  custom_webhook: [{ value: "send_data", label: "Send Data" }],
};

const ActionConfig: React.FC<ActionConfigProps> = ({
  workflowId,
  component,
}) => {
  const queryClient = useQueryClient();
  const [showActionConfig, setShowActionConfig] = useState(true);
  const configRef = useRef<ActionConfigData | null>(null);
  const [config, setConfig] = useState<ActionConfigData>({
    system: "pipedrive",
    action: "create_activity",
    standard_fields: [
      {
        id: "1",
        fieldName: "subject",
        sourceField: "follow_1_subject",
      },
      {
        id: "2",
        fieldName: "body",
        sourceField: "follow_up_1",
      },
      {
        id: "3",
        fieldName: "due_date",
        sourceField: "timeline",
      },
    ],
    custom_field_mappings: [
      {
        id: "1",
        crmField: "call_pain_points",
        sourceField: "pain_points",
      },
      {
        id: "2",
        crmField: "next_action",
        sourceField: "next_steps",
      },
    ],
  });

  // Fetch available source fields from previous components
  const { data: availableSources } = useQuery({
    queryKey: ["component-sources", component.id],
    queryFn: async () => {
      const response = await componentApi.getAvailableVariables(component.id);
      return response.data.available_variables;
    },
  });

  // Fetch available CRM fields based on selected system and action
  const { data: availableCrmFields, isLoading: fieldsLoading } = useQuery({
    queryKey: ["crm-fields", config.system, config.action],
    queryFn: async () => {
      if (config.system === "pipedrive") {
        const response = await componentApi.getPipedriveFields(config.action);
        return response.data.fields;
      }
      // For other systems, return empty array (not yet implemented)
      return [];
    },
    enabled: config.system === "pipedrive", // Only fetch if Pipedrive is selected
  });

  // Mutation to clear Pipedrive cache and refresh fields
  const refreshFieldsMutation = useMutation({
    mutationFn: () => componentApi.clearPipedriveCache(),
    onSuccess: () => {
      // Invalidate the CRM fields query to refetch
      queryClient.invalidateQueries({ queryKey: ["crm-fields", config.system, config.action] });
    },
  });

  // Keep ref in sync with config
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  useEffect(() => {
    if (component.configuration) {
      setConfig((prev) => ({
        ...prev,
        ...component.configuration,
      }));
    }
  }, [component.configuration]);

  const updateConfigMutation = useMutation({
    mutationFn: (configData: any) =>
      componentApi.updateConfig(component.id, configData),
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

  // Listen for save-configuration event from parent
  useEffect(() => {
    const handleSaveEvent = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.componentId === component.id) {
        // Use the latest config from ref
        if (configRef.current) {
          updateConfigMutation.mutate(configRef.current);
        }
      }
    };

    window.addEventListener("save-configuration", handleSaveEvent);
    return () => {
      window.removeEventListener("save-configuration", handleSaveEvent);
    };
  }, [component.id, updateConfigMutation]);

  const handleSave = async () => {
    await updateConfigMutation.mutateAsync(config);
  };

  const addStandardFieldMapping = () => {
    const newMapping: FieldMapping = {
      id: Date.now().toString(),
      fieldName: availableCrmFields?.[0]?.value || "",
      sourceField: "",
    };
    setConfig((prev) => ({
      ...prev,
      standard_fields: [...prev.standard_fields, newMapping],
    }));
  };

  const removeStandardFieldMapping = (id: string) => {
    setConfig((prev) => ({
      ...prev,
      standard_fields: prev.standard_fields.filter((m) => m.id !== id),
    }));
  };

  const updateStandardFieldMapping = (
    id: string,
    field: "fieldName" | "sourceField",
    value: string
  ) => {
    setConfig((prev) => ({
      ...prev,
      standard_fields: prev.standard_fields.map((mapping) => {
        if (mapping.id === id) {
          return {
            ...mapping,
            [field]: value,
          };
        }
        return mapping;
      }),
    }));
  };

  const addCustomFieldMapping = () => {
    const newMapping: CustomFieldMapping = {
      id: Date.now().toString(),
      crmField: "",
      sourceField: "",
    };
    setConfig((prev) => ({
      ...prev,
      custom_field_mappings: [...prev.custom_field_mappings, newMapping],
    }));
  };

  const removeCustomFieldMapping = (id: string) => {
    setConfig((prev) => ({
      ...prev,
      custom_field_mappings: prev.custom_field_mappings.filter(
        (m) => m.id !== id
      ),
    }));
  };

  const updateCustomFieldMapping = (
    id: string,
    field: "crmField" | "sourceField",
    value: string
  ) => {
    setConfig((prev) => ({
      ...prev,
      custom_field_mappings: prev.custom_field_mappings.map((mapping) => {
        if (mapping.id === id) {
          return {
            ...mapping,
            [field]: value,
          };
        }
        return mapping;
      }),
    }));
  };

  const availableActions = ACTIONS[config.system] || [];

  return (
    <div className="space-y-6">
      {/* Action Configuration */}
      <Card>
        <Collapsible open={showActionConfig} onOpenChange={setShowActionConfig}>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-gray-50 transition-colors">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-medium flex items-center">
                  <Database className="h-5 w-5 mr-2 text-blue-600" />
                  Action Configuration
                </CardTitle>
                {showActionConfig ? (
                  <ChevronDown className="h-5 w-5 text-gray-400" />
                ) : (
                  <ChevronRight className="h-5 w-5 text-gray-400" />
                )}
              </div>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="space-y-6">
              {/* System and Action Selection */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>System</Label>
                  <Select
                    value={config.system}
                    onValueChange={(value) =>
                      setConfig((prev) => ({
                        ...prev,
                        system: value as any,
                        action:
                          (ACTIONS[value as keyof typeof ACTIONS]?.[0]
                            ?.value as any) || "create_activity",
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SYSTEMS.map((system) => (
                        <SelectItem key={system.value} value={system.value}>
                          {system.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Action</Label>
                  <Select
                    value={config.action}
                    onValueChange={(value) =>
                      setConfig((prev) => ({ ...prev, action: value as any }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {availableActions.map((action) => (
                        <SelectItem key={action.value} value={action.value}>
                          {action.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Pipedrive-specific configuration */}
              {config.system === "pipedrive" && (
                <>
                  {/* Refresh Fields Button */}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => refreshFieldsMutation.mutate()}
                      disabled={refreshFieldsMutation.isPending || fieldsLoading}
                      className="text-xs"
                    >
                      {refreshFieldsMutation.isPending ? (
                        <>
                          <LoadingSpinner size="sm" className="mr-2" />
                          Refreshing...
                        </>
                      ) : (
                        <>
                          <RefreshCw className="h-3 w-3 mr-2" />
                          Refresh Fields from Pipedrive
                        </>
                      )}
                    </Button>
                    <span className="text-xs text-gray-500">
                      Use this if you added new custom fields in Pipedrive
                    </span>
                  </div>

                  {/* Standard Field Mapping */}
                  <div className="space-y-4">
                <Label className="text-sm font-semibold">
                  Standard Field Mapping
                </Label>

                <div className="space-y-3">
                  {config.standard_fields.map((mapping) => (
                    <div key={mapping.id} className="flex items-center gap-3">
                      <Select
                        value={mapping.fieldName}
                        onValueChange={(value) =>
                          updateStandardFieldMapping(
                            mapping.id,
                            "fieldName",
                            value
                          )
                        }
                      >
                        <SelectTrigger className="flex-1">
                          <SelectValue placeholder="Select CRM field..." />
                        </SelectTrigger>
                        <SelectContent>
                          {availableCrmFields?.map((field) => (
                            <SelectItem key={field.value} value={field.value}>
                              {field.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <div className="text-gray-400">
                        <ArrowRight className="h-4 w-4 rotate-180" />
                      </div>
                      <Select
                        value={mapping.sourceField}
                        onValueChange={(value) =>
                          updateStandardFieldMapping(
                            mapping.id,
                            "sourceField",
                            value
                          )
                        }
                      >
                        <SelectTrigger className="flex-1">
                          <SelectValue placeholder="Select source..." />
                        </SelectTrigger>
                        <SelectContent>
                          {availableSources?.map((source) => (
                            <SelectItem key={source.value} value={source.value}>
                              {source.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeStandardFieldMapping(mapping.id)}
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  ))}

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={addStandardFieldMapping}
                    className="w-full"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Add standard field mapping
                  </Button>
                </div>
              </div>

              {/* Custom Field Mapping */}
              <div className="space-y-4">
                <Label className="text-sm font-semibold">
                  Custom Field Mapping
                </Label>

                <div className="space-y-3">
                  {config.custom_field_mappings.map((mapping) => (
                    <div key={mapping.id} className="flex items-center gap-3">
                      <Input
                        placeholder="CRM Field Name"
                        value={mapping.crmField}
                        onChange={(e) =>
                          updateCustomFieldMapping(
                            mapping.id,
                            "crmField",
                            e.target.value
                          )
                        }
                        className="flex-1"
                      />
                      <div className="text-gray-400">
                        <ArrowRight className="h-4 w-4 rotate-180" />
                      </div>
                      <Select
                        value={mapping.sourceField}
                        onValueChange={(value) =>
                          updateCustomFieldMapping(
                            mapping.id,
                            "sourceField",
                            value
                          )
                        }
                      >
                        <SelectTrigger className="flex-1">
                          <SelectValue placeholder="Select source..." />
                        </SelectTrigger>
                        <SelectContent>
                          {availableSources?.map((source) => (
                            <SelectItem key={source.value} value={source.value}>
                              {source.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeCustomFieldMapping(mapping.id)}
                      >
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                  ))}

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={addCustomFieldMapping}
                    className="w-full"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Add custom field mapping
                  </Button>
                </div>

                    <p className="text-xs text-gray-500">
                      Note: Custom fields must exist in{" "}
                      {SYSTEMS.find((s) => s.value === config.system)?.label} before
                      mapping
                    </p>
                  </div>
                </>
              )}
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      {/* Webhook Configuration */}
      {config.system === "custom_webhook" && (
        <WebhookConfig workflowId={workflowId} component={component} />
      )}

    </div>
  );
};

export default ActionConfig;
