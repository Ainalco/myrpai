/**
 * SCURRY FRONTEND UPDATE - PipelineSidebar.tsx
 * ============================================
 * REPLACES: frontend/src/components/processing/PipelineSidebar.tsx
 *
 * WHAT CHANGED (1 change only):
 * - Non-selected pipeline components now show a visible gray border at rest
 *   instead of transparent. Hover shows orange tint. This makes the pipeline
 *   look "connected" visually - cards are always outlined, not floating.
 *
 * BACKEND IMPACT: None. This is a CSS-only change.
 * Search for "SCURRY-CHANGE" to find the exact line.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building,
  Clock,
  Database,
  FileText,
  GripVertical,
  Lock,
  Mail,
  MessageSquare,
  Plus,
  RefreshCw,
  Settings,
  Shuffle,
  Smartphone,
  Workflow,
  Zap,
} from "lucide-react";
import React, { useRef, useState } from "react";
import { useDrag, useDrop } from "react-dnd";
import { TIMING_PUNS } from "../../lib/timing-puns";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { useToast } from "@/components/ui/use-toast";
import {
  Component,
  componentApi,
  Connection,
  demoTranscriptsApi,
  executionApi,
  FirefliesTranscriptSummary,
  firefliesApi,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

interface PipelineSidebarProps {
  workflowId: number;
  components: Component[];
  connections: Connection[];
  selectedComponentId: number | null;
  onComponentSelect: (id: number) => void;
  onTestFullProcess: () => void;
  onDragStateChange?: (isDragging: boolean) => void;
}

// Icon mapping for component types
const ICON_MAP: Record<string, any> = {
  file: FileText,
  document: FileText,
  mail: Mail,
  smartphone: Smartphone,
  branch: Shuffle,
  brain: MessageSquare,
  "external-link": Database,
  filter: MessageSquare,
  building: Building,
  zap: Zap,
};

const ITEM_TYPE = "PIPELINE_COMPONENT";
const ENABLE_DEMO_TRANSCRIPTS =
  import.meta.env.VITE_ENABLE_DEMO_TRANSCRIPTS === "true";

// --- Inline Timing Labels ---

// TIMING_PUNS imported from ../../lib/timing-puns

const TIMING_COLORS = {
  instant: {
    bg: "#FF57220D",
    border: "#FF572228",
    text: "#FF5722",
    line: "#FF572233",
  },
  fixed_delay: {
    bg: "#7955480D",
    border: "#79554828",
    text: "#795548",
    line: "#79554833",
  },
  ai: {
    bg: "#7B1FA20D",
    border: "#7B1FA228",
    text: "#7B1FA2",
    line: "#7B1FA233",
  },
} as const;
const THREADING_COLORS = {
  bg: "#7B1FA20D",
  border: "#7B1FA244",
  text: "#7B1FA2",
  line: "#7B1FA244",
} as const;

const DEFAULT_LINE_COLOR = "#E8DDD7";
const THREAD_CONNECTOR_STROKE = "#7B1FA2";
const THREAD_CONNECTOR_STROKE_ACTIVE = "#5E1691";

function formatTimingLabel(value: number, unit: string): string {
  const singular = unit.replace(/s$/, "");
  return value === 1 ? `${value} ${singular}` : `${value} ${unit}`;
}

function getTimingPunCategory(timingType: string, unit: string): string {
  if (timingType === "immediate") return "instant";
  if (timingType === "ai_decides") return "ai";
  return unit || "hours";
}

function getTimingColorKey(timingType: string): keyof typeof TIMING_COLORS {
  if (timingType === "immediate") return "instant";
  if (timingType === "ai_decides") return "ai";
  return "fixed_delay";
}

function getPreSendLabel(config: any): string | null {
  const preSend = config?.pre_send_check;
  if (!preSend) return null;

  const hasCRM = preSend.condition_groups?.some((g: any) =>
    g.conditions?.some((c: any) => c.field),
  );
  const hasAI = preSend.ai_filter?.enabled;

  if (hasCRM && hasAI) return "CRM + AI";
  if (hasCRM) return "CRM Check";
  if (hasAI) return "AI Filter";
  return null;
}

const ComponentConnector: React.FC<{ component: Component; replyParentName?: string | null }> = React.memo(
  ({ component, replyParentName }) => {
    const rawTiming = component.configuration?.send_timing;
    const isEmail = component.type === "email";
    // Email components always get a timing label - default to "immediate" if not yet configured
    const timing = isEmail ? (rawTiming || "immediate") : rawTiming;
    const hasTiming = isEmail;
    const delayValue = component.configuration?.delay_value || 1;
    const delayUnit = component.configuration?.delay_unit || "hours";

    // Stable pun selection - re-picks only when timing config changes
    const configKey = `${timing}-${delayValue}-${delayUnit}`;
    const punRef = React.useRef({ key: "", pun: "" });

    if (hasTiming && punRef.current.key !== configKey) {
      const category = getTimingPunCategory(timing, delayUnit);
      const puns = TIMING_PUNS[category] || TIMING_PUNS.hours;
      const index = Math.floor(Math.random() * puns.length);
      let text = puns[index];
      if (timing === "fixed_delay") {
        text = text.replace("{time}", formatTimingLabel(delayValue, delayUnit));
      }
      punRef.current = { key: configKey, pun: text };
    }

    const preSendLabel = isEmail
      ? getPreSendLabel(component.configuration)
      : null;
    const threadLabel = replyParentName ? `Reply to ${replyParentName}` : null;

    // Standard connector when no timing and no pre-send check
    if (!hasTiming && !preSendLabel && !threadLabel) {
      return (
        <div className="flex flex-col items-center">
          {" "}
          {/* SCURRY-CHANGE: removed py-1 */}
          <div
            style={{
              width: 3.5,
              height: 16,
              backgroundColor: DEFAULT_LINE_COLOR,
            }}
          />
        </div>
      );
    }

    const colorKey = hasTiming ? getTimingColorKey(timing) : null;
    const colors = colorKey ? TIMING_COLORS[colorKey] : null;

    return (
      <div className="flex flex-col items-center">
        {" "}
        {/* SCURRY-CHANGE: removed py-1 */}
        {/* Top connector line - timing color or default */}
        <div
          style={{
            width: 3.5,
            height: 8,
            backgroundColor: colors?.line || DEFAULT_LINE_COLOR,
          }}
        />
        {/* Timing Label Pill */}
        {hasTiming && colors && (
          <div
            style={{
              padding: "4px 10px",
              borderRadius: 6,
              fontSize: 9.5,
              fontWeight: 600,
              textAlign: "center",
              backgroundColor: colors.bg,
              border: `1px solid ${colors.border}`,
              color: colors.text,
              lineHeight: 1.3,
            }}
          >
            {punRef.current.pun}
          </div>
        )}
        {/* Pre-Send Check Label */}
        {preSendLabel && (
          <>
            {hasTiming && (
              <div
                style={{
                  width: 3.5,
                  height: 4,
                  backgroundColor: colors?.line || DEFAULT_LINE_COLOR,
                }}
              />
            )}
            <div
              style={{
                padding: "3px 8px",
                borderRadius: 6,
                fontSize: 8.5,
                fontWeight: 600,
                textAlign: "center",
                backgroundColor: "#4CAF500D",
                border: "1px solid #4CAF5028",
                color: "#4CAF50",
                lineHeight: 1.3,
              }}
            >
               Checks: {preSendLabel}
            </div>
          </>
        )}
        {/* Bottom connector line - default color */}
        {threadLabel && (
          <>
            {(hasTiming || preSendLabel) && (
              <div
                style={{
                  width: 3.5,
                  height: 4,
                  backgroundColor: THREADING_COLORS.line,
                }}
              />
            )}
            <div
              style={{
                padding: "3px 8px",
                borderRadius: 999,
                fontSize: 8.5,
                fontWeight: 700,
                textAlign: "center",
                backgroundColor: THREADING_COLORS.bg,
                border: `1px dashed ${THREADING_COLORS.border}`,
                color: THREADING_COLORS.text,
                lineHeight: 1.3,
              }}
              title={`Threaded as reply to ${replyParentName}`}
            >
              Thread: {replyParentName}
            </div>
          </>
        )}
        <div
          style={{
            width: 3.5,
            height: 8,
            backgroundColor: DEFAULT_LINE_COLOR,
          }}
        />
      </div>
    );
  },
);

interface DraggableComponentProps {
  component: Component;
  index: number;
  isSelected: boolean;
  Icon: React.ElementType;
  isInputSource: boolean;
  onComponentSelect: (id: number) => void;
  onMoveComponent: (dragIndex: number, hoverIndex: number) => void;
  onDrop: () => void;
  onDragStateChange?: (isDragging: boolean) => void;
}

const DraggableComponent: React.FC<DraggableComponentProps> = ({
  component,
  index,
  isSelected,
  Icon,
  isInputSource,
  onComponentSelect,
  onMoveComponent,
  onDrop,
  onDragStateChange,
}) => {
  const ref = useRef<HTMLDivElement>(null);

  const [{ handlerId }, drop] = useDrop({
    accept: ITEM_TYPE,
    collect(monitor) {
      return {
        handlerId: monitor.getHandlerId(),
      };
    },
    hover(item: any, monitor) {
      if (!ref.current) {
        return;
      }

      const dragIndex = item.index;
      const hoverIndex = index;

      // Don't replace items with themselves
      if (dragIndex === hoverIndex) {
        return;
      }

      // Don't allow moving items to position 0 (Input Source position)
      if (hoverIndex === 0) {
        return;
      }

      // Don't allow Input Source (index 0) to be moved
      if (dragIndex === 0) {
        return;
      }

      // Determine rectangle on screen
      const hoverBoundingRect = ref.current?.getBoundingClientRect();

      // Get vertical middle
      const hoverMiddleY =
        (hoverBoundingRect.bottom - hoverBoundingRect.top) / 2;

      // Determine mouse position
      const clientOffset = monitor.getClientOffset();

      // Get pixels to the top
      const hoverClientY = clientOffset!.y - hoverBoundingRect.top;

      // Only perform the move when the mouse has crossed half of the items height
      // When dragging downwards, only move when the cursor is below 50%
      // When dragging upwards, only move when the cursor is above 50%

      // Dragging downwards
      if (dragIndex < hoverIndex && hoverClientY < hoverMiddleY) {
        return;
      }

      // Dragging upwards
      if (dragIndex > hoverIndex && hoverClientY > hoverMiddleY) {
        return;
      }

      // Time to actually perform the action
      onMoveComponent(dragIndex, hoverIndex);

      // Note: we're mutating the monitor item here!
      // Generally it's better to avoid mutations,
      // but it's good here for the sake of performance
      // to avoid expensive index searches.
      item.index = hoverIndex;
    },
  });

  const [{ isDragging }, drag, preview] = useDrag({
    type: ITEM_TYPE,
    item: () => {
      // Notify parent when drag starts
      if (onDragStateChange) {
        onDragStateChange(true);
      }
      return { id: component.id, index };
    },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
    canDrag: !isInputSource, // Input Source cannot be dragged
    end: (item, monitor) => {
      // Notify parent when drag ends
      if (onDragStateChange) {
        onDragStateChange(false);
      }

      const didDrop = monitor.didDrop();
      if (didDrop) {
        // Call onDrop to persist the order changes
        onDrop();
      }
    },
  });

  const opacity = isDragging ? 0.4 : 1;

  // Only attach drag handle if not Input Source
  if (!isInputSource) {
    drag(drop(ref));
  } else {
    drop(ref);
  }

  return (
    <div ref={ref} style={{ opacity }} data-handler-id={handlerId}>
      <div
        className={`cursor-pointer transition-all p-3 border-2 rounded-xl ${
          isSelected
            ? "border-scurry-orange bg-scurry-orange-light"
            : "border-scurry-gray-border hover:border-scurry-orange/40 bg-white" /* SCURRY-CHANGE: persistent border instead of transparent */
        } ${!isInputSource && "hover:shadow-sm"}`}
        onClick={() => onComponentSelect(component.id)}
      >
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3 flex-1">
            {!isInputSource && (
              <div className="cursor-move text-scurry-latte pt-1">
                <GripVertical className="h-4 w-4" />
              </div>
            )}
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                isSelected ? "bg-scurry-orange" : "bg-scurry-orange/10"
              }`}
            >
              <Icon
                className={`h-4 w-4 ${isSelected ? "text-white" : "text-scurry-orange"}`}
              />
            </div>
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-display font-semibold text-scurry-espresso truncate">
                {component.name}
              </h4>
              <p className="text-xs text-scurry-latte mt-1">
                {component.description || component.type.replace("_", " ")}
              </p>
              {component.configuration?.last_run && (
                <p className="text-xs text-scurry-latte/75 mt-1">
                  Last run: {component.configuration.last_run}
                </p>
              )}
            </div>
          </div>
          {isInputSource && (
            <div
              className="text-scurry-latte p-1"
              title="Required component - cannot be moved or deleted"
            >
              <Lock className="h-4 w-4" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const PipelineSidebar: React.FC<PipelineSidebarProps> = ({
  workflowId,
  components,
  connections,
  selectedComponentId,
  onComponentSelect,
  onTestFullProcess,
  onDragStateChange,
}) => {
  const [addComponentOpen, setAddComponentOpen] = useState(false);
  const [transcriptSelectOpen, setTranscriptSelectOpen] = useState(false);
  const [selectedTranscriptId, setSelectedTranscriptId] = useState<
    string | null
  >(null);
  const [localComponents, setLocalComponents] = useState<Component[]>([]);
  const [threadOverlaySize, setThreadOverlaySize] = useState({
    width: 0,
    height: 0,
  });
  const [threadPaths, setThreadPaths] = useState<
    Array<{
      key: string;
      parentId: number;
      childId: number;
      d: string;
      parentY: number;
      childY: number;
      parentName: string;
      childName: string;
    }>
  >([]);
  const listContentRef = useRef<HTMLDivElement>(null);
  const componentCardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const queryClient = useQueryClient();
  const { toast } = useToast();

  // Fetch Fireflies transcripts
  const { data: transcripts, isLoading: transcriptsLoading } = useQuery({
    queryKey: ["fireflies-transcripts"],
    queryFn: () => firefliesApi.listTranscripts().then((res) => res.data),
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
    enabled: transcriptSelectOpen,
  });

  // Load demo transcripts only when the feature flag is enabled.
  const { data: demoTranscripts } = useQuery({
    queryKey: ["demo-transcripts"],
    queryFn: () => demoTranscriptsApi.list().then((res) => res.data),
    staleTime: 60 * 60 * 1000, // 1 hour
    enabled: transcriptSelectOpen && ENABLE_DEMO_TRANSCRIPTS,
  });

  const allTranscripts = React.useMemo(() => {
    const fireflies: FirefliesTranscriptSummary[] = transcripts || [];
    if (!ENABLE_DEMO_TRANSCRIPTS) return fireflies;

    const demos: FirefliesTranscriptSummary[] = (demoTranscripts || []).map(
      (demo: {
        id: string;
        title: string;
        duration: number;
        participants?: string[];
      }) => ({
        id: demo.id,
        title: `[Demo] ${demo.title}`,
        date: undefined,
        duration: demo.duration,
        participants: demo.participants || [],
        participant_count: demo.participants?.length || 0,
      }),
    );

    return [...demos, ...fireflies];
  }, [demoTranscripts, transcripts]);

  // Fetch available component types from API (filtered by user permissions)
  const { data: componentTypesData } = useQuery({
    queryKey: ["component-types"],
    queryFn: () => componentApi.getTypes().then((res) => res.data),
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Transform component types data to include icon components
  const availableComponentTypes = React.useMemo(() => {
    if (!componentTypesData) return [];

    return Object.entries(componentTypesData)
      .filter(([key]) => key !== "input_sources") // Exclude input_sources from add dialog
      .map(([type, data]) => ({
        type,
        name: data.name,
        description: data.description,
        icon: ICON_MAP[data.icon] || FileText, // Fallback to FileText if icon not found
      }));
  }, [componentTypesData]);

  const handleDragStateChange = (isDragging: boolean) => {
    if (onDragStateChange) {
      onDragStateChange(isDragging);
    }
  };

  // Initialize local components when components prop changes
  React.useEffect(() => {
    setLocalComponents([...components].sort((a, b) => a.order - b.order));
  }, [components]);

  const createComponentMutation = useMutation({
    mutationFn: (data: { type: string; name: string; description?: string }) =>
      componentApi.create(workflowId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      setAddComponentOpen(false);
    },
  });

  const updateComponentOrderMutation = useMutation({
    mutationFn: async (updates: { componentId: number; order: number }[]) => {
      // Update each component's order
      await Promise.all(
        updates.map((update) =>
          componentApi.update(workflowId, update.componentId, {
            order: update.order,
          }),
        ),
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["components", workflowId] });
      toast({
        title: "Success",
        description: "Component order updated successfully!",
      });
    },
    onError: () => {
      // Revert on error
      setLocalComponents([...components].sort((a, b) => a.order - b.order));
      toast({
        title: "Error",
        description: "Failed to update component order. Please try again.",
        variant: "destructive",
      });
    },
  });

  const executeWorkflowMutation = useMutation({
    mutationFn: (transcriptId?: string) =>
      executionApi.execute(workflowId, true, transcriptId), // true = test mode
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["latest-execution", workflowId],
      });
      setTranscriptSelectOpen(false);
      setSelectedTranscriptId(null);
      onTestFullProcess(); // This will open the TestResultsModal
    },
  });

  const handleExecuteWorkflow = () => {
    if (selectedTranscriptId) {
      executeWorkflowMutation.mutate(selectedTranscriptId);
    } else {
      // Execute without transcript
      executeWorkflowMutation.mutate();
    }
  };

  const handleAddComponent = (componentType: any) => {
    createComponentMutation.mutate({
      type: componentType.type,
      name: componentType.name,
      description: componentType.description,
    });
  };

  const moveComponent = (dragIndex: number, hoverIndex: number) => {
    const draggedComponent = localComponents[dragIndex];
    const newComponents = [...localComponents];

    // Remove the dragged component
    newComponents.splice(dragIndex, 1);
    // Insert it at the new position
    newComponents.splice(hoverIndex, 0, draggedComponent);

    setLocalComponents(newComponents);
  };

  const handleDrop = () => {
    // Prepare updates with new order values
    const updates = localComponents.map((comp, index) => ({
      componentId: comp.id,
      order: index,
    }));

    // Only update if order actually changed
    const hasOrderChanged = localComponents.some(
      (comp, index) => comp.order !== index,
    );
    if (hasOrderChanged) {
      updateComponentOrderMutation.mutate(updates);
    }
  };

  const getComponentIcon = (type: string) => {
    // Get icon from componentTypesData if available
    if (componentTypesData && componentTypesData[type]) {
      const iconName = componentTypesData[type].icon;
      return ICON_MAP[iconName] || Settings;
    }
    return Settings;
  };

  const threadingLinks = React.useMemo(() => {
    const idToComponent = new Map(localComponents.map((component) => [component.id, component]));
    const idToIndex = new Map(localComponents.map((component, index) => [component.id, index]));

    return localComponents
      .filter((component) => {
        const parentId = component.configuration?.thread_parent_component_id;
        return (
          component.type === "email" &&
          component.configuration?.send_as === "reply_to_component" &&
          typeof parentId === "number"
        );
      })
      .map((component) => {
        const parentId = component.configuration?.thread_parent_component_id as number;
        const parentComponent = idToComponent.get(parentId);
        if (!parentComponent) return null;

        const parentIndex = idToIndex.get(parentId);
        const childIndex = idToIndex.get(component.id);
        if (
          typeof parentIndex !== "number" ||
          typeof childIndex !== "number" ||
          parentIndex >= childIndex
        ) {
          return null;
        }

        return {
          parentId,
          childId: component.id,
          parentName: parentComponent.name,
          childName: component.name,
        };
      })
      .filter(
        (
          link,
        ): link is {
          parentId: number;
          childId: number;
          parentName: string;
          childName: string;
        } => Boolean(link),
      );
  }, [localComponents]);

  const recomputeThreadPaths = React.useCallback(() => {
    const container = listContentRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.scrollHeight;
    setThreadOverlaySize({ width, height });

    if (threadingLinks.length === 0) {
      setThreadPaths([]);
      return;
    }

    const xMain = 16;
    const xCurve = 4;
    const xChildStub = 28;
    const xParentStub = 26;

    const nextPaths = threadingLinks
      .map((link) => {
        const parentCard = componentCardRefs.current[link.parentId];
        const childCard = componentCardRefs.current[link.childId];
        if (!parentCard || !childCard) return null;

        const parentY = parentCard.offsetTop + parentCard.offsetHeight / 2;
        const childY = childCard.offsetTop + childCard.offsetHeight / 2;
        const d = [
          `M ${xParentStub} ${parentY}`,
          `L ${xMain} ${parentY}`,
          `C ${xCurve} ${parentY}, ${xCurve} ${childY}, ${xMain} ${childY}`,
          `L ${xChildStub} ${childY}`,
        ].join(" ");

        return {
          key: `${link.parentId}-${link.childId}`,
          parentId: link.parentId,
          childId: link.childId,
          d,
          parentY,
          childY,
          parentName: link.parentName,
          childName: link.childName,
        };
      })
      .filter(
        (
          path,
        ): path is {
          key: string;
          parentId: number;
          childId: number;
          d: string;
          parentY: number;
          childY: number;
          parentName: string;
          childName: string;
        } => Boolean(path),
      );

    setThreadPaths(nextPaths);
  }, [threadingLinks]);

  React.useLayoutEffect(() => {
    const frame = window.requestAnimationFrame(recomputeThreadPaths);
    return () => window.cancelAnimationFrame(frame);
  }, [recomputeThreadPaths, localComponents]);

  React.useEffect(() => {
    const onResize = () => recomputeThreadPaths();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [recomputeThreadPaths]);

  return (
    <div className="h-full flex flex-col">
      {/* Header - matches Layout sidebar */}
      <div className="flex h-16 shrink-0 items-center px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-scurry-orange flex-shrink-0">
          <Workflow className="h-5 w-5 text-white" />
        </div>
        <span className="ml-2 text-lg font-semibold text-scurry-espresso truncate">
          Processing Pipeline
        </span>
        <div
          className="ml-auto flex items-center"
          title="Dotted purple lines show reply-thread links between emails."
        >
          <span className="inline-block h-px w-4 border-t border-dashed border-[#7B1FA2]" />
        </div>
      </div>

      {/* Add Component */}
      <div className="px-6 pb-3">
        <p className="text-xs text-scurry-latte mb-2">
          {components.length} components ready to scurry!
        </p>
        <Dialog open={addComponentOpen} onOpenChange={setAddComponentOpen}>
          <DialogTrigger asChild>
            <Button className="w-full bg-gradient-to-br from-scurry-orange to-scurry-orange-hover hover:from-scurry-orange-hover hover:to-scurry-orange-hover text-white font-semibold rounded-lg shadow-lg shadow-scurry-orange/25">
              <Plus className="h-4 w-4 mr-2" />
              Add Component
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="font-display text-lg font-bold text-scurry-espresso">
                Add Component 
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-2 mt-4">
              {availableComponentTypes.map((componentType) => {
                const Icon = componentType.icon;
                return (
                  <button
                    key={componentType.type}
                    onClick={() => handleAddComponent(componentType)}
                    disabled={createComponentMutation.isPending}
                    className="w-full text-left p-3.5 border border-transparent rounded-xl hover:border-scurry-orange/25 hover:bg-scurry-orange-light transition-all disabled:opacity-50"
                  >
                    <div className="flex items-start space-x-3.5">
                      <div className="w-10 h-10 bg-scurry-orange/10 rounded-xl flex items-center justify-center flex-shrink-0">
                        <Icon className="h-5 w-5 text-scurry-orange" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="font-display font-semibold text-scurry-espresso">
                          {componentType.name}
                        </h4>
                        <p className="text-sm text-scurry-latte mt-1">
                          {componentType.description}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Components List */}
      <div className="flex-1 overflow-y-auto px-4">
        {localComponents.length === 0 ? (
          <div className="text-center py-6">
            <p className="text-sm text-scurry-latte">No components yet</p>
          </div>
        ) : (
          <div ref={listContentRef} className="relative">
            {threadPaths.length > 0 && (
              <svg
                width={threadOverlaySize.width}
                height={threadOverlaySize.height}
                className="pointer-events-none absolute left-0 top-0 z-10"
              >
                {threadPaths.map((path) => (
                  <g key={path.key}>
                    <title>{`${path.childName} replies to ${path.parentName}`}</title>
                    <path
                      d={path.d}
                      fill="none"
                      stroke={
                        selectedComponentId === path.parentId || selectedComponentId === path.childId
                          ? THREAD_CONNECTOR_STROKE_ACTIVE
                          : THREAD_CONNECTOR_STROKE
                      }
                      strokeWidth={
                        selectedComponentId === path.parentId || selectedComponentId === path.childId
                          ? 2
                          : 1.5
                      }
                      strokeDasharray="4 4"
                      strokeLinecap="round"
                    />
                    <circle
                      cx={28}
                      cy={path.parentY}
                      r={2}
                      fill={
                        selectedComponentId === path.parentId || selectedComponentId === path.childId
                          ? THREAD_CONNECTOR_STROKE_ACTIVE
                          : THREAD_CONNECTOR_STROKE
                      }
                    />
                    <circle
                      cx={28}
                      cy={path.childY}
                      r={2}
                      fill={
                        selectedComponentId === path.parentId || selectedComponentId === path.childId
                          ? THREAD_CONNECTOR_STROKE_ACTIVE
                          : THREAD_CONNECTOR_STROKE
                      }
                    />
                  </g>
                ))}
              </svg>
            )}
            {" "}
            {/* SCURRY-CHANGE: removed space-y-2 so connector lines touch card borders */}
            {localComponents.map((component, index) => {
              const Icon = getComponentIcon(component.type);
              const isSelected = component.id === selectedComponentId;
              const isInputSource = component.type === "input_sources";
              const replyParentId = component.configuration?.thread_parent_component_id;
              const replyParentName =
                component.configuration?.send_as === "reply_to_component" && replyParentId
                  ? localComponents.find((candidate) => candidate.id === replyParentId)?.name || null
                  : null;

              return (
                <div key={component.id}>
                  <div
                    ref={(node) => {
                      componentCardRefs.current[component.id] = node;
                    }}
                  >
                    <DraggableComponent
                      component={component}
                      index={index}
                      isSelected={isSelected}
                      Icon={Icon}
                      isInputSource={isInputSource}
                      onComponentSelect={onComponentSelect}
                      onMoveComponent={moveComponent}
                      onDrop={handleDrop}
                      onDragStateChange={handleDragStateChange}
                    />
                  </div>

                  {/* Connection Arrow + Timing Label */}
                  {index < localComponents.length - 1 && (
                    <ComponentConnector component={component} replyParentName={replyParentName} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Test Button */}
      <div className="px-6 py-3 border-t border-scurry-gray-border">
        <Dialog
          open={transcriptSelectOpen}
          onOpenChange={setTranscriptSelectOpen}
        >
          <DialogTrigger asChild>
            <Button
              className="w-full bg-gradient-to-br from-scurry-green to-[#43A047] hover:from-[#43A047] hover:to-[#388E3C] text-white font-semibold rounded-lg shadow-lg shadow-scurry-green/30"
              disabled={
                components.length === 0 || executeWorkflowMutation.isPending
              }
            >
              {executeWorkflowMutation.isPending ? (
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Zap className="h-4 w-4 mr-2" />
              )}
              {executeWorkflowMutation.isPending
                ? "Running..."
                : "Test Full Process"}
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
            <DialogHeader>
              <DialogTitle className="font-display text-lg font-bold text-scurry-espresso">
                Select Fireflies Transcript
              </DialogTitle>
            </DialogHeader>

            <div className="flex-1 overflow-y-auto mt-4">
              {transcriptsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <LoadingSpinner />
                </div>
              ) : allTranscripts.length > 0 ? (
                <div className="space-y-2">
                  {allTranscripts.map((transcript) => (
                    <button
                      key={transcript.id}
                      onClick={() => setSelectedTranscriptId(transcript.id)}
                      className={`w-full text-left p-4 border-2 rounded-xl transition-all ${
                        selectedTranscriptId === transcript.id
                          ? "border-scurry-orange bg-scurry-orange-light"
                          : "border-transparent hover:border-scurry-latte/25 hover:bg-scurry-foam"
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 min-w-0">
                          <h4 className="font-semibold text-scurry-espresso truncate">
                            {transcript.title}
                          </h4>
                          <div className="flex items-center gap-2 mt-1 text-sm text-scurry-latte">
                            <Clock className="h-3.5 w-3.5" />
                            <span>
                              {transcript.date
                                ? formatRelativeTime(new Date(transcript.date))
                                : "Demo transcript"}
                            </span>
                            {transcript.date && <span>•</span>}
                            <span>{Math.round(transcript.duration)} min</span>
                          </div>
                          {transcript.participants &&
                            transcript.participants.length > 0 && (
                              <p className="text-sm text-scurry-latte mt-1">
                                {transcript.participants.slice(0, 3).join(", ")}
                                {transcript.participants.length > 3 &&
                                  ` +${transcript.participants.length - 3} more`}
                              </p>
                            )}
                        </div>
                        {selectedTranscriptId === transcript.id && (
                          <div className="ml-3 flex-shrink-0">
                            <div className="w-5 h-5 bg-scurry-orange rounded-full flex items-center justify-center">
                              <svg
                                className="w-3 h-3 text-white"
                                fill="currentColor"
                                viewBox="0 0 20 20"
                              >
                                <path
                                  fillRule="evenodd"
                                  d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                  clipRule="evenodd"
                                />
                              </svg>
                            </div>
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <p className="text-scurry-latte">
                    No Fireflies transcripts found
                  </p>
                  <p className="text-sm text-scurry-latte/75 mt-1">
                    Connect your Fireflies account in Settings
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 mt-4 pt-4 border-t border-scurry-foam">
              <Button
                variant="outline"
                onClick={() => {
                  setTranscriptSelectOpen(false);
                  setSelectedTranscriptId(null);
                }}
                className="border-scurry-latte/25 text-scurry-espresso"
              >
                Cancel
              </Button>
              <Button
                onClick={handleExecuteWorkflow}
                disabled={
                  !selectedTranscriptId || executeWorkflowMutation.isPending
                }
                className="bg-gradient-to-br from-scurry-green to-[#43A047] hover:from-[#43A047] hover:to-[#388E3C] text-white font-semibold shadow-lg shadow-scurry-green/30"
              >
                {executeWorkflowMutation.isPending ? (
                  <>
                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Zap className="h-4 w-4 mr-2" />
                    Run with Selected Transcript
                  </>
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
        <p className="text-xs text-scurry-latte text-center mt-2">
           Run all components in sequence
        </p>
      </div>
    </div>
  );
};

export default PipelineSidebar;
