import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Zap, Lightbulb, Layers, ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Component, componentApi } from "@/lib/api";

interface AdvancedActionConfigProps {
  workflowId: number;
  component: Component;
}

interface AdvancedActionConfigData {
  deal_id_source: string;
  field_to_update: string;
  update_value: string;
}

const AdvancedActionConfig: React.FC<AdvancedActionConfigProps> = ({
  workflowId,
  component,
}) => {
  const queryClient = useQueryClient();
  const [showConfig, setShowConfig] = useState(true);
  const configRef = useRef<AdvancedActionConfigData | null>(null);
  const [config, setConfig] = useState<AdvancedActionConfigData>({
    deal_id_source: "{{matched_deal_id}}",
    field_to_update: "",
    update_value: "",
  });
  const [showDealIdSuggestions, setShowDealIdSuggestions] = useState(false);
  const [showValueSuggestions, setShowValueSuggestions] = useState(false);
  const dealIdInputRef = useRef<HTMLInputElement>(null);
  const valueInputRef = useRef<HTMLInputElement>(null);

  // Fetch available variables from previous components
  const { data: availableVariables } = useQuery({
    queryKey: ["component-variables", component.id],
    queryFn: async () => {
      const response = await componentApi.getAvailableVariables(component.id);
      return response.data.available_variables;
    },
  });

  // Fetch Pipedrive deal fields
  const { data: pipedriveFields, isLoading: fieldsLoading } = useQuery({
    queryKey: ["pipedrive-fields", "update_deal"],
    queryFn: async () => {
      const response = await componentApi.getPipedriveFields("update_deal");
      return response.data.fields;
    },
  });

  // Refresh fields mutation
  const refreshFieldsMutation = useMutation({
    mutationFn: () => componentApi.clearPipedriveCache(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pipedrive-fields", "update_deal"] });
    },
  });

  // Keep ref in sync with config
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  useEffect(() => {
    if (component.configuration && Object.keys(component.configuration).length > 0) {
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
      const event = new CustomEvent("configuration-saved", {
        detail: { componentId: component.id, success: true },
      });
      window.dispatchEvent(event);
    },
    onError: () => {
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

  // Handle input to detect {{ for variable suggestions (Deal ID)
  const handleDealIdInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setConfig((prev) => ({ ...prev, deal_id_source: value }));

    const cursorPos = e.target.selectionStart || 0;
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastTwoChars = textBeforeCursor.slice(-2);

    if (lastTwoChars === "{{") {
      setShowDealIdSuggestions(true);
    } else if (!textBeforeCursor.endsWith("{")) {
      setShowDealIdSuggestions(false);
    }
  };

  // Handle input to detect {{ for variable suggestions (Update Value)
  const handleValueInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setConfig((prev) => ({ ...prev, update_value: value }));

    const cursorPos = e.target.selectionStart || 0;
    const textBeforeCursor = value.substring(0, cursorPos);
    const lastTwoChars = textBeforeCursor.slice(-2);

    if (lastTwoChars === "{{") {
      setShowValueSuggestions(true);
    } else if (!textBeforeCursor.endsWith("{")) {
      setShowValueSuggestions(false);
    }
  };

  // Insert variable at cursor position (Deal ID)
  const insertDealIdVariable = (variableValue: string) => {
    if (!dealIdInputRef.current) return;

    const input = dealIdInputRef.current;
    const currentValue = config.deal_id_source || "";
    const cursorPos = input.selectionStart || 0;

    const textBeforeCursor = currentValue.substring(0, cursorPos);
    const lastBraceIndex = textBeforeCursor.lastIndexOf("{{");

    if (lastBraceIndex !== -1) {
      const newValue =
        currentValue.substring(0, lastBraceIndex) +
        `{{${variableValue}}}` +
        currentValue.substring(cursorPos);

      setConfig((prev) => ({ ...prev, deal_id_source: newValue }));
      setShowDealIdSuggestions(false);

      setTimeout(() => {
        const newCursorPos = lastBraceIndex + variableValue.length + 4;
        input.selectionStart = newCursorPos;
        input.selectionEnd = newCursorPos;
        input.focus();
      }, 0);
    }
  };

  // Insert variable at cursor position (Update Value)
  const insertValueVariable = (variableValue: string) => {
    if (!valueInputRef.current) return;

    const input = valueInputRef.current;
    const currentValue = config.update_value || "";
    const cursorPos = input.selectionStart || 0;

    const textBeforeCursor = currentValue.substring(0, cursorPos);
    const lastBraceIndex = textBeforeCursor.lastIndexOf("{{");

    if (lastBraceIndex !== -1) {
      const newValue =
        currentValue.substring(0, lastBraceIndex) +
        `{{${variableValue}}}` +
        currentValue.substring(cursorPos);

      setConfig((prev) => ({ ...prev, update_value: newValue }));
      setShowValueSuggestions(false);

      setTimeout(() => {
        const newCursorPos = lastBraceIndex + variableValue.length + 4;
        input.selectionStart = newCursorPos;
        input.selectionEnd = newCursorPos;
        input.focus();
      }, 0);
    }
  };

  // Close suggestions when clicking outside
  useEffect(() => {
    const handleClickOutside = () => {
      setShowDealIdSuggestions(false);
      setShowValueSuggestions(false);
    };
    if (showDealIdSuggestions || showValueSuggestions) {
      document.addEventListener("click", handleClickOutside);
      return () => document.removeEventListener("click", handleClickOutside);
    }
  }, [showDealIdSuggestions, showValueSuggestions]);

  return (
    <div className="space-y-6">
      {/* Advanced Action Configuration */}
      <Card>
        <Collapsible open={showConfig} onOpenChange={setShowConfig}>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-gray-50 transition-colors">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-medium flex items-center">
                  <Zap className="h-5 w-5 mr-2 text-yellow-600" />
                  Advanced Action Configuration
                </CardTitle>
                {showConfig ? (
                  <ChevronDown className="h-5 w-5 text-gray-400" />
                ) : (
                  <ChevronRight className="h-5 w-5 text-gray-400" />
                )}
              </div>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="space-y-6">
              {/* Deal ID Source */}
              <div className="space-y-2 relative">
                <Label className="text-sm font-semibold">
                  Deal ID
                </Label>
                <p className="text-xs text-gray-500 mb-2">
                  Reference the deal ID to update. Typically from Advanced Matching component.
                </p>
                <Input
                  ref={dealIdInputRef}
                  placeholder={'{{matched_deal_id}}'}
                  value={config.deal_id_source}
                  onChange={handleDealIdInput}
                  className="font-mono text-sm"
                />

                {/* Variable Suggestions Dropdown - Deal ID */}
                {showDealIdSuggestions &&
                  availableVariables &&
                  availableVariables.length > 0 && (
                    <div
                      className="absolute z-50 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto"
                      onMouseDown={(e) => e.preventDefault()}
                    >
                      <div className="p-2 border-b border-gray-100 bg-gray-50">
                        <div className="flex items-center gap-2 text-xs text-gray-600">
                          <Lightbulb className="h-3 w-3" />
                          <span>Available Variables</span>
                        </div>
                      </div>
                      <div className="p-1">
                        {availableVariables.map((variable: any, index: number) => (
                          <button
                            key={index}
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              insertDealIdVariable(variable.value);
                            }}
                            className="w-full text-left px-3 py-2 hover:bg-blue-50 rounded flex items-center gap-2 group"
                          >
                            <Layers className="h-4 w-4 text-blue-600" />
                            <div className="flex-1">
                              <div className="text-sm font-medium text-gray-900">
                                {variable.value}
                              </div>
                              {variable.label && (
                                <div className="text-xs text-gray-500">
                                  {variable.label}
                                </div>
                              )}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                <p className="text-xs text-gray-500">
                  <strong>Tip:</strong> Type <code className="bg-gray-100 px-1 py-0.5 rounded">{"{{"}</code> to insert variables.
                </p>
              </div>

              {/* Field to Update */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-semibold">
                    Field to Update
                  </Label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => refreshFieldsMutation.mutate()}
                    disabled={refreshFieldsMutation.isPending}
                    className="h-6 text-xs"
                  >
                    <RefreshCw className={`h-3 w-3 mr-1 ${refreshFieldsMutation.isPending ? 'animate-spin' : ''}`} />
                    Refresh Fields
                  </Button>
                </div>
                <p className="text-xs text-gray-500 mb-2">
                  Select which Pipedrive deal field to update.
                </p>
                <Select
                  value={config.field_to_update}
                  onValueChange={(value) =>
                    setConfig((prev) => ({ ...prev, field_to_update: value }))
                  }
                  disabled={fieldsLoading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a field..." />
                  </SelectTrigger>
                  <SelectContent>
                    {pipedriveFields && pipedriveFields.length > 0 ? (
                      pipedriveFields.map((field: any) => (
                        <SelectItem key={field.value} value={field.value}>
                          {field.label}
                          {field.is_custom && <span className="ml-2 text-xs text-gray-500">(Custom)</span>}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem value="no-fields" disabled>
                        No fields available
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
              </div>

              {/* Update Value */}
              <div className="space-y-2 relative">
                <Label className="text-sm font-semibold">
                  New Value
                </Label>
                <p className="text-xs text-gray-500 mb-2">
                  The value to set for this field. Can use variables or literal values.
                </p>
                <Input
                  ref={valueInputRef}
                  placeholder="Enter new value or {{variable}}"
                  value={config.update_value}
                  onChange={handleValueInput}
                  className="font-mono text-sm"
                />

                {/* Variable Suggestions Dropdown - Update Value */}
                {showValueSuggestions &&
                  availableVariables &&
                  availableVariables.length > 0 && (
                    <div
                      className="absolute z-50 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto"
                      onMouseDown={(e) => e.preventDefault()}
                    >
                      <div className="p-2 border-b border-gray-100 bg-gray-50">
                        <div className="flex items-center gap-2 text-xs text-gray-600">
                          <Lightbulb className="h-3 w-3" />
                          <span>Available Variables</span>
                        </div>
                      </div>
                      <div className="p-1">
                        {availableVariables.map((variable: any, index: number) => (
                          <button
                            key={index}
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              insertValueVariable(variable.value);
                            }}
                            className="w-full text-left px-3 py-2 hover:bg-blue-50 rounded flex items-center gap-2 group"
                          >
                            <Layers className="h-4 w-4 text-blue-600" />
                            <div className="flex-1">
                              <div className="text-sm font-medium text-gray-900">
                                {variable.value}
                              </div>
                              {variable.label && (
                                <div className="text-xs text-gray-500">
                                  {variable.label}
                                </div>
                              )}
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                <p className="text-xs text-gray-500">
                  <strong>Tip:</strong> Type <code className="bg-gray-100 px-1 py-0.5 rounded">{"{{"}</code> to insert variables.
                </p>
              </div>

              {/* How It Works */}
              <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 space-y-2">
                <p className="text-sm font-semibold text-yellow-900">
                  How Advanced Action Works:
                </p>
                <ol className="text-xs text-yellow-800 space-y-1 list-decimal list-inside">
                  <li>
                    Resolves the Deal ID from variable or literal value
                  </li>
                  <li>
                    Substitutes any variables in the update value
                  </li>
                  <li>
                    Updates the specified field on the Pipedrive deal
                  </li>
                  <li>
                    Returns success confirmation with updated field info
                  </li>
                </ol>
              </div>

              {/* Requirements */}
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-xs text-amber-800">
                  <strong>Requirements:</strong> This component requires:
                </p>
                <ul className="text-xs text-amber-800 space-y-1 mt-1 list-disc list-inside">
                  <li>Pipedrive API key configured in Settings</li>
                  <li>Valid deal ID (from variable or literal)</li>
                  <li>Selected field must exist in Pipedrive</li>
                </ul>
              </div>
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

    </div>
  );
};

export default AdvancedActionConfig;
