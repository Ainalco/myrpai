import { useQuery, useQueryClient } from '@tanstack/react-query';

export interface ComponentTestResult {
  componentId: number;
  testResults: any;
  timestamp: number;
}

// Query key factory
export const componentTestKeys = {
  all: ['component-test-results'] as const,
  workflow: (workflowId: number) =>
    [...componentTestKeys.all, workflowId] as const,
  component: (workflowId: number, componentId: number) =>
    [...componentTestKeys.workflow(workflowId), componentId] as const,
  // Workflow-level shared transcript selection
  transcript: (workflowId: number) =>
    ['workflow-test-transcript', workflowId] as const,
};

// localStorage key helpers
const testResultStorageKey = (workflowId: number, componentId: number) =>
  `scurry-test-result-${workflowId}-${componentId}`;

const transcriptStorageKey = (workflowId: number) =>
  `scurry-test-transcript-${workflowId}`;

function readTestResultFromStorage(
  workflowId: number,
  componentId: number
): ComponentTestResult | undefined {
  try {
    const stored = localStorage.getItem(testResultStorageKey(workflowId, componentId));
    if (!stored) return undefined;
    return JSON.parse(stored) as ComponentTestResult;
  } catch {
    return undefined;
  }
}

export const useComponentTestResults = (
  workflowId: number,
  componentId: number
) => {
  const queryClient = useQueryClient();

  // Get cached test results per component (seeded from localStorage if cache is empty)
  const { data: cachedResults } = useQuery<ComponentTestResult | null>({
    queryKey: componentTestKeys.component(workflowId, componentId),
    queryFn: () => null, // Never fetches, just reads cache
    enabled: false, // Disabled - we only use cache
    staleTime: 30 * 60 * 1000, // 30 minutes
    gcTime: 30 * 60 * 1000, // Keep in cache for 30 minutes
    // Seed from localStorage when cache is empty (e.g. after page navigation)
    initialData: () => readTestResultFromStorage(workflowId, componentId),
  });

  // Get shared transcript selection (workflow-level, seeded from localStorage)
  const { data: sharedTranscriptId } = useQuery<string | null>({
    queryKey: componentTestKeys.transcript(workflowId),
    queryFn: () => null,
    enabled: false,
    staleTime: 30 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    initialData: () => {
      try {
        return localStorage.getItem(transcriptStorageKey(workflowId)) ?? undefined;
      } catch {
        return undefined;
      }
    },
  });

  const setTestResults = (data: Partial<ComponentTestResult>) => {
    const existing = queryClient.getQueryData<ComponentTestResult>(
      componentTestKeys.component(workflowId, componentId)
    );

    const newData = {
      ...existing,
      componentId,
      ...data,
      timestamp: Date.now(),
    };

    queryClient.setQueryData(
      componentTestKeys.component(workflowId, componentId),
      newData
    );

    // Persist to localStorage for cross-session and cross-navigation persistence
    try {
      localStorage.setItem(
        testResultStorageKey(workflowId, componentId),
        JSON.stringify(newData)
      );
    } catch {
      // localStorage may be full or unavailable
    }
  };

  const setSelectedTranscriptId = (transcriptId: string) => {
    queryClient.setQueryData(
      componentTestKeys.transcript(workflowId),
      transcriptId
    );
    try {
      localStorage.setItem(transcriptStorageKey(workflowId), transcriptId);
    } catch {
      // localStorage may be unavailable
    }
  };

  const clearTestResults = () => {
    queryClient.removeQueries({
      queryKey: componentTestKeys.component(workflowId, componentId),
    });
    try {
      localStorage.removeItem(testResultStorageKey(workflowId, componentId));
    } catch {
      // ignore
    }
  };

  const clearAllWorkflowTests = () => {
    queryClient.removeQueries({
      queryKey: componentTestKeys.workflow(workflowId),
    });
    // Clear all component test results for this workflow from localStorage
    try {
      const prefix = `scurry-test-result-${workflowId}-`;
      Object.keys(localStorage)
        .filter(key => key.startsWith(prefix))
        .forEach(key => localStorage.removeItem(key));
      localStorage.removeItem(transcriptStorageKey(workflowId));
    } catch {
      // ignore
    }
  };

  return {
    testResults: cachedResults?.testResults ?? null,
    testResultTimestamp: cachedResults?.timestamp ?? null,
    selectedTranscriptId: sharedTranscriptId ?? '',
    setTestResults,
    setSelectedTranscriptId,
    clearTestResults,
    clearAllWorkflowTests,
  };
};
