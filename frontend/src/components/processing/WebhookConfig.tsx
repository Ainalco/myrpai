import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, Plus, Save, Trash2, Send } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { Component, componentApi } from "@/lib/api";
import { Switch } from "@/components/ui/switch";

interface WebhookConfigProps {
  workflowId: number;
  component: Component;
}

interface CustomHeader {
  id: string;
  name: string;
  value: string;
}

interface WebhookConfigData {
  system: "custom_webhook";
  webhook_url: string;
  http_method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  auth_type: "none" | "bearer" | "basic" | "api_key";
  auth_config: {
    token?: string;
    username?: string;
    password?: string;
    header_name?: string;
    key?: string;
  };
  custom_headers: CustomHeader[];
  body_template: string;
  test_dry_run: boolean;
}

const HTTP_METHODS = [
  { value: "GET", label: "GET" },
  { value: "POST", label: "POST" },
  { value: "PUT", label: "PUT" },
  { value: "PATCH", label: "PATCH" },
  { value: "DELETE", label: "DELETE" },
];

const AUTH_TYPES = [
  { value: "none", label: "No Authentication" },
  { value: "bearer", label: "Bearer Token" },
  { value: "basic", label: "Basic Auth (Username/Password)" },
  { value: "api_key", label: "API Key Header" },
];

const WebhookConfig: React.FC<WebhookConfigProps> = ({
  workflowId,
  component,
}) => {
  const configRef = useRef<WebhookConfigData | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [isTesting, setIsTesting] = useState(false);

  const [config, setConfig] = useState<WebhookConfigData>({
    system: "custom_webhook",
    webhook_url: "",
    http_method: "POST",
    auth_type: "none",
    auth_config: {},
    custom_headers: [
      {
        id: "1",
        name: "Content-Type",
        value: "application/json",
      },
    ],
    body_template: '{\n  "data": "{{extracted_information}}"\n}',
    test_dry_run: true,
  });

  // Fetch available source fields from previous components
  const { data: availableSources } = useQuery({
    queryKey: ["component-sources", component.id],
    queryFn: async () => {
      const response = await componentApi.getAvailableVariables(component.id);
      return response.data.available_variables;
    },
  });

  // Keep ref in sync with config
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  // Load saved configuration from component
  useEffect(() => {
    if (component.configuration) {
      try {
        const savedConfig =
          typeof component.configuration === "string"
            ? JSON.parse(component.configuration)
            : component.configuration;

        if (savedConfig.system === "custom_webhook") {
          setConfig({
            system: "custom_webhook",
            webhook_url: savedConfig.webhook_url || "",
            http_method: savedConfig.http_method || "POST",
            auth_type: savedConfig.auth_type || "none",
            auth_config: savedConfig.auth_config || {},
            custom_headers: savedConfig.custom_headers || [
              { id: "1", name: "Content-Type", value: "application/json" },
            ],
            body_template:
              savedConfig.body_template ||
              '{\n  "data": "{{extracted_information}}"\n}',
            test_dry_run: savedConfig.test_dry_run !== false,
          });
        }
      } catch (err) {
        console.error("Failed to parse component configuration:", err);
      }
    }
  }, [component.configuration]);

  // Auto-save configuration
  useEffect(() => {
    const saveConfig = async () => {
      try {
        await componentApi.updateConfig(component.id, config);
      } catch (error) {
        console.error("Failed to auto-save configuration:", error);
      }
    };

    const debounceTimer = setTimeout(saveConfig, 1000);
    return () => clearTimeout(debounceTimer);
  }, [config, component.id]);

  const handleConfigChange = (field: keyof WebhookConfigData, value: any) => {
    setConfig((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleAuthConfigChange = (field: string, value: string) => {
    setConfig((prev) => ({
      ...prev,
      auth_config: {
        ...prev.auth_config,
        [field]: value,
      },
    }));
  };

  const addCustomHeader = () => {
    const newHeader: CustomHeader = {
      id: Date.now().toString(),
      name: "",
      value: "",
    };
    setConfig((prev) => ({
      ...prev,
      custom_headers: [...prev.custom_headers, newHeader],
    }));
  };

  const removeCustomHeader = (id: string) => {
    setConfig((prev) => ({
      ...prev,
      custom_headers: prev.custom_headers.filter((h) => h.id !== id),
    }));
  };

  const updateCustomHeader = (
    id: string,
    field: "name" | "value",
    value: string
  ) => {
    setConfig((prev) => ({
      ...prev,
      custom_headers: prev.custom_headers.map((h) =>
        h.id === id ? { ...h, [field]: value } : h
      ),
    }));
  };

  const insertVariable = (variable: string) => {
    const placeholder = `{{${variable}}}`;
    // Insert into body template at cursor position or append
    setConfig((prev) => ({
      ...prev,
      body_template: prev.body_template + "\n" + placeholder,
    }));
  };

  const handleTestWebhook = async () => {
    setIsTesting(true);
    setTestResult(null);

    try {
      const response = await componentApi.test(component.id, {
        test_data: {
          workflow_id: workflowId,
          test_mode: true,
        },
      });
      setTestResult(response.data);
    } catch (error: any) {
      setTestResult({
        success: false,
        error: error.response?.data?.detail || error.message,
      });
    } finally {
      setIsTesting(false);
    }
  };

  const formatJson = () => {
    try {
      const parsed = JSON.parse(config.body_template);
      const formatted = JSON.stringify(parsed, null, 2);
      handleConfigChange("body_template", formatted);
    } catch (err) {
      // Invalid JSON, ignore
    }
  };

  return (
    <div className="space-y-6">
      {/* Webhook URL */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Webhook Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="webhook_url">Webhook URL *</Label>
            <Input
              id="webhook_url"
              type="url"
              placeholder="https://api.example.com/endpoint"
              value={config.webhook_url}
              onChange={(e) => handleConfigChange("webhook_url", e.target.value)}
              className="mt-1"
            />
            <p className="text-sm text-muted-foreground mt-1">
              Supports variable substitution: {"{"}
              {"{"}variable_name{"}}"}
            </p>
          </div>

          <div>
            <Label htmlFor="http_method">HTTP Method *</Label>
            <Select
              value={config.http_method}
              onValueChange={(value) => handleConfigChange("http_method", value)}
            >
              <SelectTrigger id="http_method" className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HTTP_METHODS.map((method) => (
                  <SelectItem key={method.value} value={method.value}>
                    {method.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Authentication */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Authentication</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="auth_type">Authentication Type</Label>
            <Select
              value={config.auth_type}
              onValueChange={(value: any) => {
                handleConfigChange("auth_type", value);
                // Clear auth config when changing type
                handleConfigChange("auth_config", {});
              }}
            >
              <SelectTrigger id="auth_type" className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUTH_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Bearer Token */}
          {config.auth_type === "bearer" && (
            <div>
              <Label htmlFor="bearer_token">Bearer Token *</Label>
              <div className="relative mt-1">
                <Input
                  id="bearer_token"
                  type={showToken ? "text" : "password"}
                  placeholder="your-api-token"
                  value={config.auth_config.token || ""}
                  onChange={(e) => handleAuthConfigChange("token", e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShowToken(!showToken)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showToken ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                Supports variables: {"{"}
                {"{"}api_token{"}}"}
              </p>
            </div>
          )}

          {/* Basic Auth */}
          {config.auth_type === "basic" && (
            <>
              <div>
                <Label htmlFor="basic_username">Username *</Label>
                <Input
                  id="basic_username"
                  type="text"
                  placeholder="username"
                  value={config.auth_config.username || ""}
                  onChange={(e) =>
                    handleAuthConfigChange("username", e.target.value)
                  }
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="basic_password">Password *</Label>
                <div className="relative mt-1">
                  <Input
                    id="basic_password"
                    type={showPassword ? "text" : "password"}
                    placeholder="password"
                    value={config.auth_config.password || ""}
                    onChange={(e) =>
                      handleAuthConfigChange("password", e.target.value)
                    }
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
            </>
          )}

          {/* API Key */}
          {config.auth_type === "api_key" && (
            <>
              <div>
                <Label htmlFor="api_key_header">Header Name *</Label>
                <Input
                  id="api_key_header"
                  type="text"
                  placeholder="X-API-Key"
                  value={config.auth_config.header_name || ""}
                  onChange={(e) =>
                    handleAuthConfigChange("header_name", e.target.value)
                  }
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="api_key_value">API Key *</Label>
                <div className="relative mt-1">
                  <Input
                    id="api_key_value"
                    type={showToken ? "text" : "password"}
                    placeholder="your-api-key"
                    value={config.auth_config.key || ""}
                    onChange={(e) => handleAuthConfigChange("key", e.target.value)}
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken(!showToken)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showToken ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Custom Headers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Custom Headers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {config.custom_headers.map((header) => (
            <div key={header.id} className="flex gap-2 items-end">
              <div className="flex-1">
                <Label htmlFor={`header-name-${header.id}`}>Header Name</Label>
                <Input
                  id={`header-name-${header.id}`}
                  type="text"
                  placeholder="Content-Type"
                  value={header.name}
                  onChange={(e) =>
                    updateCustomHeader(header.id, "name", e.target.value)
                  }
                  className="mt-1"
                />
              </div>
              <div className="flex-1">
                <Label htmlFor={`header-value-${header.id}`}>Value</Label>
                <Input
                  id={`header-value-${header.id}`}
                  type="text"
                  placeholder="application/json"
                  value={header.value}
                  onChange={(e) =>
                    updateCustomHeader(header.id, "value", e.target.value)
                  }
                  className="mt-1"
                />
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => removeCustomHeader(header.id)}
              >
                <Trash2 size={16} />
              </Button>
            </div>
          ))}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addCustomHeader}
            className="w-full"
          >
            <Plus size={16} className="mr-2" />
            Add Header
          </Button>
        </CardContent>
      </Card>

      {/* Payload Template */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg">Payload Template</CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={formatJson}
            >
              Format JSON
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="body_template">Request Body (JSON)</Label>
            <Textarea
              id="body_template"
              rows={10}
              placeholder='{\n  "field": "{{variable_name}}"\n}'
              value={config.body_template}
              onChange={(e) => handleConfigChange("body_template", e.target.value)}
              className="mt-1 font-mono text-sm"
            />
            <p className="text-sm text-muted-foreground mt-1">
              Use {"{"}
              {"{"}variable_name{"}}"}  for variable substitution
            </p>
          </div>

          {/* Available Variables */}
          {availableSources && availableSources.length > 0 && (
            <div>
              <Label>Available Variables</Label>
              <div className="flex flex-wrap gap-2 mt-2">
                {availableSources.map((source: any) => (
                  <button
                    key={source.value || source}
                    type="button"
                    onClick={() => insertVariable(source.value || source)}
                    className="px-3 py-1 text-sm bg-secondary hover:bg-secondary/80 rounded-md transition-colors"
                  >
                    {source.label || source.value || source}
                  </button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Test Section */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Test Webhook</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Switch
                id="test_dry_run"
                checked={config.test_dry_run}
                onCheckedChange={(checked) =>
                  handleConfigChange("test_dry_run", checked)
                }
              />
              <Label htmlFor="test_dry_run" className="cursor-pointer">
                Dry-run mode (preview without sending)
              </Label>
            </div>
            <Button
              type="button"
              onClick={handleTestWebhook}
              disabled={isTesting || !config.webhook_url}
            >
              {isTesting ? (
                <LoadingSpinner size={16} className="mr-2" />
              ) : (
                <Send size={16} className="mr-2" />
              )}
              {config.test_dry_run ? "Preview Request" : "Send Test Request"}
            </Button>
          </div>

          {testResult && (
            <div className="mt-4">
              <div
                className={`p-4 rounded-md ${
                  testResult.success
                    ? "bg-green-50 dark:bg-green-900/20"
                    : "bg-red-50 dark:bg-red-900/20"
                }`}
              >
                <h4 className="font-semibold mb-2">
                  {testResult.success ? "✓ Success" : "✗ Error"}
                </h4>
                <pre className="text-sm overflow-auto max-h-96 bg-background/50 p-3 rounded">
                  {JSON.stringify(testResult, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default WebhookConfig;
