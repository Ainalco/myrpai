import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import VariableTextEditor from "@/components/ui/variable-text-editor";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Component, componentApi } from "@/lib/api";
import { ChevronDown, ChevronRight } from "lucide-react";

interface AIFilterConfigProps {
  workflowId: number;
  component: Component;
}

type AIFilterModel = "sonnet" | "haiku";

interface AIFilterConfigData {
  ai_prompt: string;
  condition_operator: string;
  condition_value: string;
  case_sensitive: boolean;
  model: AIFilterModel;
}

const CONDITION_OPERATORS = [
  { value: "contains", label: "Contains" },
  { value: "not_contains", label: "Does Not Contain" },
  { value: "equals", label: "Equals" },
  { value: "not_equals", label: "Not Equals" },
  { value: "starts_with", label: "Starts With" },
  { value: "ends_with", label: "Ends With" },
  { value: "greater_than", label: "Greater Than" },
  { value: "less_than", label: "Less Than" },
  { value: "matches_regex", label: "Matches Regex" },
  { value: "positive_sentiment", label: "Has Positive Sentiment" },
  { value: "negative_sentiment", label: "Has Negative Sentiment" },
  { value: "neutral_sentiment", label: "Has Neutral Sentiment" },
];

const AIFilterConfig: React.FC<AIFilterConfigProps> = ({
  workflowId,
  component,
}) => {
  const queryClient = useQueryClient();
  const [showConfig, setShowConfig] = useState(true);
  const configRef = useRef<AIFilterConfigData | null>(null);
  const [config, setConfig] = useState<AIFilterConfigData>({
    ai_prompt: "Analyze the following information and determine if the client shows high buying intent. Return 'high intent', 'medium intent', or 'low intent' based on their engagement, questions, and interest level.",
    condition_operator: "contains",
    condition_value: "high intent",
    case_sensitive: false,
    model: "haiku",
  });

  // Keep ref in sync with config
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  useEffect(() => {
    if (component.configuration && Object.keys(component.configuration).length > 0) {
      const storedModel = (component.configuration as { model?: string }).model;
      const normalizedModel: AIFilterModel =
        storedModel === "haiku" || storedModel === "sonnet" ? storedModel : "sonnet";
      setConfig((prev) => ({
        ...prev,
        ...component.configuration,
        model: normalizedModel,
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

  // Check if value input should be disabled (for sentiment operators)
  const isValueDisabled = [
    "positive_sentiment",
    "negative_sentiment",
    "neutral_sentiment",
  ].includes(config.condition_operator);

  return (
    <div className="space-y-6">
      {/* AI Filter Configuration */}
      <Card>
        <Collapsible open={showConfig} onOpenChange={setShowConfig}>
          <CollapsibleTrigger asChild>
            <CardHeader className="cursor-pointer hover:bg-scurry-foam/50 transition-colors">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-medium flex items-center">
                  <Brain className="h-5 w-5 mr-2 text-scurry-orange" />
                  AI Filter Configuration
                </CardTitle>
                {showConfig ? (
                  <ChevronDown className="h-5 w-5 text-scurry-latte" />
                ) : (
                  <ChevronRight className="h-5 w-5 text-scurry-latte" />
                )}
              </div>
            </CardHeader>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <CardContent className="space-y-6">
              {/* AI Analysis Prompt */}
              <div className="space-y-2">
                <Label className="text-sm font-semibold">
                  AI Analysis Prompt
                </Label>
                <p className="text-xs text-scurry-latte mb-2">
                  Write a prompt that instructs the AI to analyze your data and
                  return a specific response that can be evaluated.
                </p>
                <VariableTextEditor
                  value={config.ai_prompt}
                  onChange={(value) => setConfig((prev) => ({ ...prev, ai_prompt: value }))}
                  workflowId={workflowId}
                  componentId={component.id}
                  rows={6}
                  placeholder="Example: Analyze the transcript and determine the client's buying intent level. Return 'high intent', 'medium intent', or 'low intent' based on their engagement and questions. For numeric comparisons: 'Rate the urgency from 0-100'."
                />
                <p className="text-xs text-scurry-latte">
                  <strong>Tip:</strong> For numeric comparisons, ask the AI to
                  return a number (e.g., "Rate the urgency from 0-100"). Type <code className="bg-scurry-foam px-1 py-0.5 rounded">{"{{"}</code> to insert variables.
                </p>
              </div>

              {/* Model Selection */}
              <div className="space-y-2">
                <Label className="text-sm font-semibold">Model</Label>
                <p className="text-xs text-scurry-latte mb-2">
                  Haiku is ~10× cheaper and fine for yes/no classification. Switch to
                  Sonnet for nuanced classifiers (sentiment, intent, qualification).
                </p>
                <Select
                  value={config.model}
                  onValueChange={(value) =>
                    setConfig((prev) => ({
                      ...prev,
                      model: value as AIFilterModel,
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="haiku">Claude Haiku (fast, cheap)</SelectItem>
                    <SelectItem value="sonnet">Claude Sonnet (more accurate)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Proceed Condition */}
              <div className="space-y-4">
                <Label className="text-sm font-semibold">
                  Proceed Condition
                </Label>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label className="text-xs text-scurry-latte">
                      If AI response
                    </Label>
                    <Select
                      value={config.condition_operator}
                      onValueChange={(value) =>
                        setConfig((prev) => ({
                          ...prev,
                          condition_operator: value,
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CONDITION_OPERATORS.map((op) => (
                          <SelectItem key={op.value} value={op.value}>
                            {op.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs text-scurry-latte">
                      Value to check
                    </Label>
                    <Input
                      placeholder={
                        isValueDisabled
                          ? "Not required for sentiment checks"
                          : "Enter value..."
                      }
                      value={config.condition_value}
                      onChange={(e) =>
                        setConfig((prev) => ({
                          ...prev,
                          condition_value: e.target.value,
                        }))
                      }
                      disabled={isValueDisabled}
                    />
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="case-sensitive"
                    checked={config.case_sensitive}
                    onCheckedChange={(checked) =>
                      setConfig((prev) => ({
                        ...prev,
                        case_sensitive: checked as boolean,
                      }))
                    }
                  />
                  <Label
                    htmlFor="case-sensitive"
                    className="text-sm font-normal cursor-pointer"
                  >
                    Case sensitive
                  </Label>
                </div>
              </div>

              {/* Example Use Cases */}
              <div className="bg-scurry-foam border border-scurry-orange/20 rounded-lg p-4 space-y-2">
                <p className="text-sm font-semibold text-scurry-espresso">
                  Example Use Cases:
                </p>
                <ul className="text-xs text-scurry-latte space-y-1">
                  <li>
                    • <strong>Text Match:</strong> Check if AI detects "high
                    buying intent" in the conversation
                  </li>
                  <li>
                    • <strong>Numeric:</strong> Verify confidence score is
                    greater than 0.8
                  </li>
                  <li>
                    • <strong>Sentiment:</strong> Only proceed if sentiment is
                    positive
                  </li>
                  <li>
                    • <strong>Exclusion:</strong> Stop if response contains "not
                    interested" or "later"
                  </li>
                  <li>
                    • <strong>Pattern:</strong> Match responses that follow
                    specific formats with regex
                  </li>
                </ul>
              </div>

              {/* Important Note */}
              <div className="bg-scurry-orange-light border border-scurry-orange/20 rounded-lg p-3">
                <p className="text-xs text-scurry-latte">
                  <strong>Note:</strong> Make sure to save your configuration before testing. The AI Filter requires a configured prompt and condition to run.
                </p>
              </div>
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

    </div>
  );
};

export default AIFilterConfig;
