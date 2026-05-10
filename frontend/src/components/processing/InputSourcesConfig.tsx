import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Flame,
  Lock,
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Component, componentApi } from "@/lib/api";

interface InputSourcesConfigProps {
  workflowId: number;
  component: Component;
}

interface Integration {
  id: string;
  name: string;
  icon: React.ReactNode;
  description: string;
  available: boolean;
  comingSoon?: boolean;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "fireflies",
    name: "Fireflies.ai",
    icon: <Flame className="h-4 w-4" />,
    description: "Automatically capture and transcribe meetings",
    available: true,
  },
  // {
  //   id: 'zoom',
  //   name: 'Zoom',
  //   icon: <Video className="h-4 w-4" />,
  //   description: 'Direct integration with Zoom recordings',
  //   available: false,
  //   comingSoon: true
  // },
  // {
  //   id: 'rev',
  //   name: 'Rev',
  //   icon: <Mic className="h-4 w-4" />,
  //   description: 'Professional transcription service',
  //   available: false,
  //   comingSoon: true
  // },
  // {
  //   id: 'notion',
  //   name: 'Notion',
  //   icon: <FileText className="h-4 w-4" />,
  //   description: 'Sync with Notion meeting notes',
  //   available: false,
  //   comingSoon: true
  // },
  // {
  //   id: 'calendly',
  //   name: 'Calendly',
  //   icon: <Calendar className="h-4 w-4" />,
  //   description: 'Connect with Calendly events',
  //   available: false,
  //   comingSoon: true
  // }
];

const InputSourcesConfig: React.FC<InputSourcesConfigProps> = ({
  workflowId,
  component,
}) => {
  const [enabledIntegrations, setEnabledIntegrations] = useState<
    Record<string, boolean>
  >({});
  const [expandedSections, setExpandedSections] = useState<
    Record<string, boolean>
  >({});
  const [webhookUrls, setWebhookUrls] = useState<Record<string, string>>({});
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Form for Fireflies settings
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm({
    defaultValues: {
      fireflies_webhook_name: "Fireflies Integration",
      fireflies_webhook_description:
        "Automatically process meeting transcripts from Fireflies.ai",
    },
  });

  // Load existing configuration
  useEffect(() => {
    if (component.configuration?.integrations) {
      const integrations = component.configuration.integrations;
      const enabled: Record<string, boolean> = {};

      Object.keys(integrations).forEach((key) => {
        enabled[key] = integrations[key].enabled || false;
        if (integrations[key].webhook_url) {
          setWebhookUrls((prev) => ({
            ...prev,
            [key]: integrations[key].webhook_url,
          }));
        }
      });

      setEnabledIntegrations(enabled);

      // Set form values for existing configurations
      if (integrations.fireflies) {
        setValue(
          "fireflies_webhook_name",
          integrations.fireflies.webhook_name || "Fireflies Integration"
        );
        setValue(
          "fireflies_webhook_description",
          integrations.fireflies.webhook_description || ""
        );
      }
    }
  }, [component.configuration, setValue]);

  // Check for existing webhooks
  const { data: existingWebhooks } = useQuery({
    queryKey: ["webhooks", workflowId],
    queryFn: async () => {
      const API_BASE_URL =
        import.meta.env.VITE_API_URL || "http://localhost:9000";
      const response = await fetch(`${API_BASE_URL}/webhooks/${workflowId}`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token")}`, // Note: should be access_token not token
        },
      });
      if (!response.ok) return [];
      const webhooks = await response.json();
      return webhooks.filter((w: any) => w.component_id === component.id);
    },
    enabled: component.type === "input_sources",
  });

  useEffect(() => {
    if (existingWebhooks && existingWebhooks.length > 0) {
      existingWebhooks.forEach((webhook: any) => {
        if (webhook.name?.includes("Fireflies")) {
          setWebhookUrls((prev) => ({
            ...prev,
            fireflies: webhook.webhook_url,
          }));
        }
      });
    }
  }, [existingWebhooks]);

  const updateConfigMutation = useMutation({
    mutationFn: async (config: any) => {
      return componentApi.updateConfig(component.id, config);
    },
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
        handleSubmit(onSubmit)();
      }
    };

    window.addEventListener("save-configuration", handleSaveEvent);
    return () => {
      window.removeEventListener("save-configuration", handleSaveEvent);
    };
  }, [component.id]);

  const createWebhookMutation = useMutation({
    mutationFn: async (integrationId: string) => {
      const API_BASE_URL =
        import.meta.env.VITE_API_URL || "http://localhost:9000";
      const response = await fetch(`${API_BASE_URL}/webhooks/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("access_token")}`, // Note: should be access_token not token
        },
        body: JSON.stringify({
          workflow_id: workflowId,
          component_id: component.id,
          name: `${integrationId} Webhook`,
          description: `Webhook for ${integrationId} integration`,
        }),
      });
      if (!response.ok) throw new Error("Failed to create webhook");
      return response.json();
    },
    onSuccess: (data, integrationId) => {
      setWebhookUrls((prev) => ({
        ...prev,
        [integrationId]: data.webhook_url,
      }));
      queryClient.invalidateQueries({ queryKey: ["webhooks", workflowId] });
    },
  });

  const toggleIntegration = async (integrationId: string) => {
    const integration = INTEGRATIONS.find((i) => i.id === integrationId);
    if (!integration?.available) return;

    const newState = !enabledIntegrations[integrationId];
    setEnabledIntegrations((prev) => ({ ...prev, [integrationId]: newState }));

    let webhookUrl = webhookUrls[integrationId];

    // Auto-expand when enabling
    if (newState) {
      setExpandedSections((prev) => ({ ...prev, [integrationId]: true }));

      // Create webhook if enabling Fireflies and no webhook exists
      if (integrationId === "fireflies" && !webhookUrls[integrationId]) {
        const webhookData = await createWebhookMutation.mutateAsync(
          integrationId
        );
        webhookUrl = webhookData.webhook_url;
      }
    }

    // Save the state with webhook URL
    const updatedConfig = {
      ...component.configuration,
      integrations: {
        ...component.configuration?.integrations,
        [integrationId]: {
          enabled: newState,
          webhook_url: webhookUrl,
          ...(component.configuration?.integrations?.[integrationId] || {}),
        },
      },
    };

    await updateConfigMutation.mutateAsync(updatedConfig);
  };

  const toggleSection = (integrationId: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [integrationId]: !prev[integrationId],
    }));
  };

  const copyToClipboard = (url: string, integrationId: string) => {
    navigator.clipboard.writeText(url);
    setCopiedUrl(integrationId);
    setTimeout(() => setCopiedUrl(null), 2000);
  };

  const onSubmit = async (data: any) => {
    const updatedConfig = {
      ...component.configuration,
      integrations: {
        ...component.configuration?.integrations,
        fireflies: {
          enabled: enabledIntegrations.fireflies || false,
          webhook_name: data.fireflies_webhook_name,
          webhook_description: data.fireflies_webhook_description,
          webhook_url: webhookUrls.fireflies,
        },
      },
    };

    await updateConfigMutation.mutateAsync(updatedConfig);
  };

  return (
    <div className="space-y-6">
      {/* Available Integrations */}
      <div>
        <h3 className="text-sm font-semibold text-scurry-espresso mb-1">
          Available Integrations
        </h3>
        <p className="text-xs text-scurry-latte mb-4">Connect your meeting tools - we'll catch every transcript! 🎯</p>
        <div className="grid grid-cols-1 gap-3">
          {INTEGRATIONS.map((integration) => (
            <Card key={integration.id} className="overflow-hidden border-scurry-foam">
              <div className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div
                      className={`w-11 h-11 rounded-xl flex items-center justify-center border ${
                        integration.available ? "bg-scurry-orange/10 border-scurry-orange/20" : "bg-gray-100 border-gray-200"
                      }`}
                    >
                      <span className={integration.available ? "text-scurry-orange" : "text-gray-400"}>
                        {integration.icon}
                      </span>
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <h4 className="text-sm font-semibold text-scurry-espresso">
                          {integration.name}
                        </h4>
                        {integration.comingSoon && (
                          <Badge variant="secondary" className="text-xs">
                            Coming Soon
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-scurry-latte">
                        {integration.description}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    {integration.available ? (
                      <>
                        <Switch
                          checked={enabledIntegrations[integration.id] || false}
                          onCheckedChange={() =>
                            toggleIntegration(integration.id)
                          }
                          disabled={updateConfigMutation.isPending}
                        />
                        {enabledIntegrations[integration.id] && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => toggleSection(integration.id)}
                            className="text-scurry-latte hover:bg-scurry-foam"
                          >
                            {expandedSections[integration.id] ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </Button>
                        )}
                      </>
                    ) : (
                      <Lock className="h-4 w-4 text-scurry-latte" />
                    )}
                  </div>
                </div>

                {/* Fireflies Settings Section */}
                {integration.id === "fireflies" &&
                  enabledIntegrations.fireflies &&
                  expandedSections.fireflies && (
                    <div className="mt-4 pt-4 border-t border-scurry-foam">
                      <form
                        onSubmit={handleSubmit(onSubmit)}
                        className="space-y-4"
                      >
                        {/* Webhook URL Display */}
                        {webhookUrls.fireflies && (
                          <div className="bg-scurry-foam/50 p-4 rounded-xl">
                            <Label className="text-xs font-semibold text-scurry-espresso">
                              🔗 Your Webhook URL
                            </Label>
                            <p className="text-xs text-scurry-latte mb-2 mt-1">
                              Copy this URL and paste it in your Fireflies webhook settings. We'll start gathering transcripts faster than a squirrel hoards acorns!
                            </p>
                            <div className="flex items-center space-x-2">
                              <code className="flex-1 p-2.5 bg-white border border-scurry-latte/20 rounded-lg text-xs font-mono break-all text-scurry-espresso">
                                {webhookUrls.fireflies}
                              </code>
                              <Button
                                type="button"
                                size="sm"
                                onClick={() =>
                                  copyToClipboard(
                                    webhookUrls.fireflies,
                                    "fireflies"
                                  )
                                }
                                className={copiedUrl === "fireflies"
                                  ? "bg-scurry-green hover:bg-scurry-green text-white"
                                  : "bg-scurry-orange hover:bg-scurry-orange-hover text-white"
                                }
                              >
                                {copiedUrl === "fireflies" ? (
                                  <><Check className="h-4 w-4 mr-1" /> Copied</>
                                ) : (
                                  <><Copy className="h-4 w-4 mr-1" /> Copy</>
                                )}
                              </Button>
                            </div>
                          </div>
                        )}

                        <div className="grid grid-cols-1 gap-4">
                          <div className="space-y-2">
                            <Label
                              htmlFor="fireflies_webhook_name"
                              className="text-xs font-medium text-scurry-espresso"
                            >
                              Webhook Name
                            </Label>
                            <Input
                              id="fireflies_webhook_name"
                              {...register("fireflies_webhook_name", {
                                required: true,
                              })}
                              className="h-9 text-sm border-scurry-latte/25"
                            />
                          </div>

                          <div className="space-y-2">
                            <Label
                              htmlFor="fireflies_webhook_description"
                              className="text-xs font-medium text-scurry-espresso"
                            >
                              Description (Optional)
                            </Label>
                            <Textarea
                              id="fireflies_webhook_description"
                              {...register("fireflies_webhook_description")}
                              rows={2}
                              className="text-sm border-scurry-latte/25"
                            />
                          </div>
                        </div>

                        <div className="flex justify-end pt-2">
                          <Button
                            type="submit"
                            size="sm"
                            disabled={updateConfigMutation.isPending}
                            className="bg-gradient-to-br from-scurry-orange to-scurry-orange-hover hover:from-scurry-orange-hover hover:to-scurry-orange-hover text-white font-semibold shadow-lg shadow-scurry-orange/25"
                          >
                            {updateConfigMutation.isPending ? (
                              <LoadingSpinner size="sm" className="mr-2" />
                            ) : null}
                            Save Settings
                          </Button>
                        </div>
                      </form>

                      {/* Setup Instructions */}
                      <div className="mt-4 p-4 bg-white rounded-xl border border-scurry-yellow/40">
                        <h5 className="text-xs font-semibold text-scurry-espresso mb-2">
                          ✨ Quick Setup (30 seconds!)
                        </h5>
                        <ol className="text-xs text-scurry-latte space-y-1.5 list-decimal list-inside">
                          <li>Go to your Fireflies.ai dashboard</li>
                          <li>Navigate to Integrations → Webhooks</li>
                          <li>Click "Add Webhook" and paste the URL above</li>
                          <li>
                            Select "Meeting Completed" as the trigger event
                          </li>
                          <li>Save and you're golden! 🥜</li>
                        </ol>
                      </div>
                    </div>
                  )}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
};

export default InputSourcesConfig;
