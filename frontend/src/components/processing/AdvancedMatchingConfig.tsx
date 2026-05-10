import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building, Lightbulb, Layers, ChevronDown, ChevronRight, Users, Building2 } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import VariableTextEditor from "@/components/ui/variable-text-editor";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Component, componentApi } from "@/lib/api";

interface AdvancedMatchingConfigProps {
  workflowId: number;
  component: Component;
}

interface AdvancedMatchingConfigData {
  ai_prompt: string;
  output_variable_name: string;
  create_if_not_found: boolean;
  create_contacts: boolean;
}

const AdvancedMatchingConfig: React.FC<AdvancedMatchingConfigProps> = ({
  workflowId,
  component,
}) => {
  const queryClient = useQueryClient();
  const [showConfig, setShowConfig] = useState(true);
  const configRef = useRef<AdvancedMatchingConfigData | null>(null);
  const [config, setConfig] = useState<AdvancedMatchingConfigData>({
    ai_prompt: "Extract the company name from {{extracted_information}}",
    output_variable_name: "matched_org_id",
    create_if_not_found: true,
    create_contacts: true,
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

  return (
    <div className="space-y-6">
      {/* Advanced Matching Configuration */}
      <Card>
        <Collapsible open={showConfig} onOpenChange={setShowConfig}>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-gray-50 transition-colors">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-medium flex items-center">
                  <Building className="h-5 w-5 mr-2 text-blue-600" />
                  Advanced Matching Configuration
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
              {/* Company Name / AI Instructions */}
              <div className="space-y-2">
                <Label className="text-sm font-semibold">
                  Company Name or AI Instructions
                </Label>
                <p className="text-xs text-gray-500 mb-2">
                  Provide either: (1) a direct company name (<code>{"{{company_name}}"}</code> or "Acme Corp"), OR (2) AI instructions to extract the company name from your data.
                </p>
                <VariableTextEditor
                  value={config.ai_prompt}
                  onChange={(value) => setConfig((prev) => ({ ...prev, ai_prompt: value }))}
                  workflowId={workflowId}
                  componentId={component.id}
                  rows={4}
                  placeholder="Examples:&#10;1. {{company_name}}&#10;2. Extract the company name from {{extracted_information}}&#10;3. Acme Corporation"
                />
                <p className="text-xs text-gray-500">
                  <strong>Tip:</strong> Type <code className="bg-gray-100 px-1 py-0.5 rounded">{"{{"}</code> to insert variables. You can use direct values (<code>{"{{company_name}}"}</code>) or write AI instructions like "Extract the organization name from <code>{"{{extracted_information}}"}</code>".
                </p>
              </div>

              {/* Output Variable Name */}
              <div className="space-y-2">
                <Label className="text-sm font-semibold">
                  Output Variable Name
                </Label>
                <p className="text-xs text-gray-500 mb-2">
                  Name of the variable that will store the matched organization ID for use in downstream components.
                </p>
                <Input
                  placeholder="matched_org_id"
                  value={config.output_variable_name}
                  onChange={(e) =>
                    setConfig((prev) => ({
                      ...prev,
                      output_variable_name: e.target.value,
                    }))
                  }
                  className="font-mono text-sm"
                />
                <p className="text-xs text-gray-500">
                  You can reference this variable in downstream components using: <code className="bg-gray-100 px-1 py-0.5 rounded">{"{{" + config.output_variable_name + "}}"}</code>
                </p>
              </div>

              {/* Organization Creation Toggle */}
              <div className="space-y-3 pt-2 border-t">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <Label className="text-sm font-semibold flex items-center">
                      <Building2 className="h-4 w-4 mr-2 text-green-600" />
                      Create Organization if Not Found
                    </Label>
                    <p className="text-xs text-gray-500">
                      When enabled, automatically creates a new organization in Pipedrive if no match is found.
                    </p>
                  </div>
                  <Switch
                    checked={config.create_if_not_found}
                    onCheckedChange={(checked) =>
                      setConfig((prev) => ({ ...prev, create_if_not_found: checked }))
                    }
                  />
                </div>
              </div>

              {/* Contact Creation Toggle */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <Label className="text-sm font-semibold flex items-center">
                      <Users className="h-4 w-4 mr-2 text-purple-600" />
                      Create Contacts for External Participants
                    </Label>
                    <p className="text-xs text-gray-500">
                      Creates Pipedrive persons for external meeting participants (filtered by your internal domains). Contacts are linked to the matched/created organization.
                    </p>
                  </div>
                  <Switch
                    checked={config.create_contacts}
                    onCheckedChange={(checked) =>
                      setConfig((prev) => ({ ...prev, create_contacts: checked }))
                    }
                  />
                </div>
              </div>

              {/* How It Works */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-2">
                <p className="text-sm font-semibold text-blue-900">
                  How Advanced Matching Works:
                </p>
                <ol className="text-xs text-blue-800 space-y-1 list-decimal list-inside">
                  <li>AI extracts the company name from your input data</li>
                  <li>Fetches organizations from Pipedrive (cached 1 hour)</li>
                  <li>AI matches the name to the best organization</li>
                  <li>If no match found and creation enabled, creates new organization</li>
                  <li>Filters external participants using your internal domains setting</li>
                  <li>Creates Pipedrive contacts for external participants, linked to org</li>
                  <li>Meeting organizer (matched to Pipedrive user by email) becomes owner</li>
                </ol>
              </div>

              {/* Requirements */}
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-xs text-amber-800">
                  <strong>Requirements:</strong> This component requires:
                </p>
                <ul className="text-xs text-amber-800 space-y-1 mt-1 list-disc list-inside">
                  <li>Pipedrive API key configured in Settings</li>
                  <li>Internal domains configured in Settings (for filtering participants)</li>
                  <li>Company name input (direct value, variable, or AI instructions)</li>
                </ul>
              </div>
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

    </div>
  );
};

export default AdvancedMatchingConfig;
