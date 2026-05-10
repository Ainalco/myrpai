import { useMutation, useQuery } from "@tanstack/react-query";
import DOMPurify from "dompurify";
import { Check, Copy, Download, Play, RefreshCw, FileCode, FileText, Mail, Clock, User, Search, ChevronDown, ChevronUp, GitBranch, Zap, Building2, BarChart3, MessageSquare, Users, Hash, Tag, ArrowRight, Shield, Lightbulb, Activity, AlertCircle } from "lucide-react";
import React, { useState, useMemo, useRef, useEffect } from "react";
import Markdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import LoadingSpinner from "@/components/ui/loading-spinner";
import { useToast } from "@/components/ui/use-toast";
import {
  componentApi,
  firefliesApi,
  demoTranscriptsApi,
  FirefliesTranscriptSummary,
  TraceEntry,
  RagTraceEntry,
} from "@/lib/api";
import { useComponentTestResults } from "@/hooks/useComponentTestResults";
import { useAuth } from "@/contexts/AuthContext";
import RagPanel from "@/components/processing/RagPanel";

interface ComponentTestUIProps {
  workflowId: number;
  componentId: number;
  componentType: string;
}

// Helper: render a value nicely based on its type
const RenderValue: React.FC<{ value: any; depth?: number }> = ({ value, depth = 0 }) => {
  if (value === null || value === undefined) {
    return <span className="text-scurry-latte italic">—</span>;
  }

  if (typeof value === 'boolean') {
    return (
      <span className={`text-xs font-semibold px-2 py-0.5 rounded ${value ? 'bg-scurry-green-light text-scurry-green' : 'bg-scurry-red-light text-scurry-red'}`}>
        {value ? 'Yes' : 'No'}
      </span>
    );
  }

  if (typeof value === 'string') {
    if (value.length > 300 && depth === 0) {
      return <TruncatedText text={value} />;
    }
    return <span className="text-sm text-scurry-espresso whitespace-pre-wrap">{value}</span>;
  }

  if (typeof value === 'number') {
    return <span className="text-sm text-scurry-espresso font-mono">{value}</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-scurry-latte italic text-sm">Empty list</span>;

    // Array of objects — render as compact cards
    if (typeof value[0] === 'object' && value[0] !== null) {
      return (
        <div className="space-y-2 mt-1">
          {value.map((item, i) => (
            <div key={i} className="bg-scurry-foam/40 rounded-lg px-3 py-2 border border-scurry-foam/60">
              {Object.entries(item).map(([k, v]) => (
                <div key={k} className="flex items-baseline gap-2 py-0.5">
                  <span className="text-xs font-medium text-scurry-latte capitalize flex-shrink-0">{k.replace(/_/g, ' ')}</span>
                  {typeof v === 'object' && v !== null ? (
                    <RenderValue value={v} depth={depth + 1} />
                  ) : (
                    <span className="text-sm text-scurry-espresso">{String(v ?? '—')}</span>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      );
    }

    // Array of primitives — render as simple list
    return (
      <ul className="space-y-1 mt-1">
        {value.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-scurry-espresso">
            <span className="text-scurry-orange mt-1.5 text-[6px]">●</span>
            {typeof item === 'object' && item !== null ? (
              <RenderValue value={item} depth={depth + 1} />
            ) : (
              <span>{String(item)}</span>
            )}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof value === 'object') {
    return (
      <div className={`space-y-1.5 ${depth > 0 ? 'mt-1 ml-3 pl-3 border-l-2 border-scurry-foam' : 'mt-1'}`}>
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="flex items-baseline gap-2">
            <span className="text-xs font-medium text-scurry-latte capitalize flex-shrink-0">{k.replace(/_/g, ' ')}</span>
            {typeof v === 'string' || typeof v === 'number' ? (
              <span className="text-sm text-scurry-espresso">{String(v)}</span>
            ) : (
              <RenderValue value={v} depth={depth + 1} />
            )}
          </div>
        ))}
      </div>
    );
  }

  // Fallback — stringify anything else to prevent React error #31
  return <span className="text-sm text-scurry-espresso">{String(value)}</span>;
};

// Truncated text component with show more/less toggle
const TruncatedText: React.FC<{ text: string }> = ({ text }) => {
  const [expanded, setExpanded] = useState(false);
  return (
    <div>
      <span className="text-sm text-scurry-espresso whitespace-pre-wrap">
        {expanded ? text : text.slice(0, 300) + '...'}
      </span>
      <button
        onClick={() => setExpanded(!expanded)}
        className="ml-1 text-xs text-scurry-orange hover:underline font-medium"
      >
        {expanded ? 'Show less' : 'Show more'}
      </button>
    </div>
  );
};

// Email-specific result card — styled like an email preview
const EmailResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const subject = results.email_subject;
  const body = results.email_body;
  const time = results.email_time;
  const recipient = results.recipient || results.recipient_email;
  const recipientName = results.recipient_name;
  const timingReason = results.timing_reason;
  const generationReason = results.generation_reason;
  const testMode = results.test_mode;
  const message = results.message;
  const emailQueued = results.email_queued;

  const emailKeys = new Set(['email_subject', 'email_body', 'email_time', 'recipient', 'recipient_email', 'recipient_name', 'email_queued', 'test_mode', 'email_id', 'message', 'scheduled_at', 'send_timing', 'timing_reason', 'generation_reason', 'status']);
  const otherFields = Object.entries(results).filter(([k]) => !emailKeys.has(k));

  const cleanBody = body
    ? String(body).replace(/\\n/g, '\n').replace(/\\r/g, '').replace(/^(Email Body:|Body:)\s*/i, '')
    : '';
  const isHtml = /<[a-z][\s\S]*>/i.test(cleanBody);

  return (
    <div className="space-y-3">
      {/* Status bar */}
      {(testMode || emailQueued) && (
        <div className="flex items-center gap-2">
          {testMode && (
            <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">
              Test Mode
            </span>
          )}
          {emailQueued && (
            <span className="text-[10px] font-bold uppercase tracking-wider text-scurry-green bg-scurry-green-light border border-scurry-green/20 px-2 py-0.5 rounded-full">
              Queued
            </span>
          )}
        </div>
      )}

      {/* Email envelope */}
      <div className="border border-gray-200 rounded-xl overflow-hidden">
        {/* Header — To / Subject / Time */}
        <div className="bg-gray-50 px-4 py-3 space-y-1.5 border-b border-gray-200">
          {(recipient || recipientName) && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[10px] font-bold text-scurry-latte uppercase w-14 flex-shrink-0">To</span>
              <div className="flex items-center gap-1.5">
                {recipientName && recipientName !== '—' && (
                  <span className="font-semibold text-scurry-espresso">{recipientName}</span>
                )}
                <span className={recipientName && recipientName !== '—' ? 'text-scurry-latte' : 'font-medium text-scurry-espresso'}>
                  {recipientName && recipientName !== '—' ? `<${recipient}>` : recipient}
                </span>
              </div>
            </div>
          )}
          {subject && (
            <div className="flex items-start gap-2 text-sm">
              <span className="text-[10px] font-bold text-scurry-latte uppercase w-14 flex-shrink-0 mt-0.5">Subject</span>
              <span className="font-semibold text-scurry-espresso">{subject}</span>
            </div>
          )}
          {time && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[10px] font-bold text-scurry-latte uppercase w-14 flex-shrink-0">Send at</span>
              <span className="text-scurry-espresso">{time}</span>
            </div>
          )}
        </div>

        {/* Body — render as HTML when AI returns HTML-formatted email */}
        {cleanBody && (
          <div className="px-4 py-4 bg-white">
            {isHtml ? (
              <div
                className="text-sm text-scurry-espresso leading-relaxed [&_a]:text-blue-600 [&_a]:underline [&_p]:my-2 [&_br]:leading-relaxed"
                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(cleanBody) }}
              />
            ) : (
              <div className="text-sm text-scurry-espresso whitespace-pre-wrap leading-relaxed">
                {cleanBody}
              </div>
            )}
          </div>
        )}
      </div>

      {/* AI Reasoning — collapsible feel */}
      {(timingReason || generationReason) && (
        <div className="bg-scurry-orange-light/40 rounded-lg p-3 border border-scurry-orange/15">
          <div className="text-[10px] font-bold text-scurry-orange uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Lightbulb className="h-3 w-3" />
            AI Reasoning
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {timingReason && (
              <div>
                <div className="text-[10px] font-semibold text-scurry-latte uppercase tracking-wide mb-0.5 flex items-center gap-1">
                  <Clock className="h-2.5 w-2.5" /> Send Timing
                </div>
                <div className="text-xs text-scurry-espresso leading-relaxed">{String(timingReason)}</div>
              </div>
            )}
            {generationReason && (
              <div>
                <div className="text-[10px] font-semibold text-scurry-latte uppercase tracking-wide mb-0.5 flex items-center gap-1">
                  <MessageSquare className="h-2.5 w-2.5" /> Content Strategy
                </div>
                <div className="text-xs text-scurry-espresso leading-relaxed">{String(generationReason)}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Status message */}
      {message && (
        <div className="text-xs text-scurry-latte italic">{message}</div>
      )}

      {/* Other fields */}
      {otherFields.length > 0 && (
        <div className="border-t border-gray-100 pt-3 space-y-2">
          <div className="text-[10px] font-bold text-scurry-latte uppercase tracking-wider">Additional Data</div>
          {otherFields.map(([key, value]) => (
            <div key={key} className="flex items-start gap-2 pb-1.5">
              <span className="text-[10px] font-semibold text-scurry-orange uppercase tracking-wide min-w-[80px] mt-0.5 flex-shrink-0">
                {key.replace(/_/g, ' ')}
              </span>
              <div className="text-sm text-scurry-espresso">
                <RenderValue value={value} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// AI Filter result view - pass/fail with AI reasoning
const AIFilterResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const passes = results.passes_filter;
  const aiResponse = results.ai_response || results.evaluation_result;
  const operator = results.condition_operator;
  const conditionValue = results.condition_value;

  const filterKeys = new Set(['passes_filter', 'ai_response', 'evaluation_result', 'condition_operator', 'condition_value']);
  const otherFields = Object.entries(results).filter(([k]) => !filterKeys.has(k));

  return (
    <div className="space-y-3">
      {/* Pass/Fail verdict */}
      <div className={`flex items-center gap-3 p-3 rounded-lg border ${
        passes ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
      }`}>
        <Shield className={`h-6 w-6 ${passes ? 'text-green-600' : 'text-red-600'}`} />
        <div>
          <div className={`text-sm font-bold ${passes ? 'text-green-800' : 'text-red-800'}`}>
            {passes ? 'Passes Filter' : 'Blocked by Filter'}
          </div>
          {operator && (
            <div className="text-xs text-scurry-latte mt-0.5">
              Condition: {operator} {conditionValue !== undefined ? `"${conditionValue}"` : ''}
            </div>
          )}
        </div>
      </div>

      {/* AI Response */}
      {aiResponse && (
        <div className="bg-scurry-foam/60 rounded-lg p-3 border border-scurry-foam">
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <MessageSquare className="h-3.5 w-3.5" />
            AI Response
          </div>
          <div className="text-sm text-scurry-espresso whitespace-pre-wrap">{String(aiResponse)}</div>
        </div>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Input Sources result view - meeting metadata + transcript
const InputSourcesResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const title = results.meeting_title;
  const date = results.meeting_date;
  const duration = results.duration;
  const participants = results.participants;
  const summary = results.summary;
  const transcript = results.transcript;
  const actionItems = results.action_items;
  const keywords = results.keywords;
  const sentiment = results.sentiment;

  const metaKeys = new Set(['meeting_title', 'meeting_date', 'duration', 'participants', 'summary', 'transcript', 'action_items', 'keywords', 'sentiment', 'meeting_url', 'organizer_email', 'source', 'meeting_id', 'sentences', 'integration']);
  const otherFields = Object.entries(results).filter(([k]) => !metaKeys.has(k));

  return (
    <div className="space-y-3">
      {/* Meeting header */}
      {title && (
        <div className="flex items-start gap-2">
          <FileText className="h-4 w-4 text-scurry-orange mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-medium text-scurry-espresso">{title}</div>
            <div className="text-xs text-scurry-latte flex items-center gap-2 mt-0.5 flex-wrap">
              {date && <span>{new Date(String(date)).toLocaleDateString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>}
              {duration && <span>• {String(duration)} min</span>}
            </div>
          </div>
        </div>
      )}

      {/* Participants */}
      {participants && Array.isArray(participants) && participants.length > 0 && (
        <div className="flex items-start gap-2">
          <Users className="h-4 w-4 text-scurry-latte mt-0.5 flex-shrink-0" />
          <div>
            <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-0.5">Participants</div>
            <div className="text-sm text-scurry-espresso space-y-0.5">
              {participants.map((p: any, i: number) => (
                <div key={i} className="flex items-center gap-1.5">
                  {typeof p === 'object' && p !== null ? (
                    <>
                      {p.name && <span className="font-medium">{p.name}</span>}
                      {p.email && <span className={p.name ? "text-scurry-latte text-xs" : ""}>{p.name ? `<${p.email}>` : p.email}</span>}
                      {p.is_organizer && <span className="text-[10px] font-medium text-scurry-orange bg-scurry-orange-light px-1.5 py-0.5 rounded-full">Organizer</span>}
                    </>
                  ) : (
                    <span>{String(p)}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sentiment */}
      {sentiment && typeof sentiment === 'object' && Object.keys(sentiment).length > 0 && (
        <div className="flex items-start gap-2">
          <BarChart3 className="h-4 w-4 text-scurry-latte mt-0.5 flex-shrink-0" />
          <div>
            <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">Sentiment</span>
            <div className="flex flex-wrap gap-1.5 mt-0.5">
              {Object.entries(sentiment).map(([key, value]) => (
                <span key={key} className="text-xs font-medium px-2 py-0.5 rounded bg-scurry-blue-bg text-scurry-blue-text">
                  {key}: {String(value)}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
      {sentiment && typeof sentiment === 'string' && (
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-scurry-latte flex-shrink-0" />
          <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">Sentiment:</span>
          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-scurry-blue-bg text-scurry-blue-text">{sentiment}</span>
        </div>
      )}

      {/* Keywords */}
      {keywords && Array.isArray(keywords) && keywords.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-1 flex items-center gap-1.5">
            <Tag className="h-3.5 w-3.5" />
            Keywords
          </div>
          <div className="flex flex-wrap gap-1.5">
            {keywords.map((kw: string, i: number) => (
              <span key={i} className="text-xs bg-scurry-foam text-scurry-espresso px-2 py-0.5 rounded-full">{kw}</span>
            ))}
          </div>
        </div>
      )}

      {/* Summary */}
      {summary && String(summary).trim() && (
        <div className="bg-scurry-foam/60 rounded-lg p-3 border border-scurry-foam">
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2">Summary</div>
          <div className="text-sm text-scurry-espresso whitespace-pre-wrap">{String(summary)}</div>
        </div>
      )}

      {/* Action Items */}
      {actionItems && Array.isArray(actionItems) && actionItems.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-1.5 flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5" />
            Action Items
          </div>
          <ul className="space-y-1">
            {actionItems.map((item: string, i: number) => (
              <li key={i} className="flex items-start gap-2 text-sm text-scurry-espresso">
                <span className="text-scurry-orange font-bold mt-0.5">•</span>
                <span>{String(item)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Transcript */}
      {transcript && (
        <details className="group">
          <summary className="text-xs font-semibold text-scurry-latte uppercase tracking-wide cursor-pointer hover:text-scurry-espresso">
            Transcript ▸
          </summary>
          <div className="mt-2 bg-scurry-foam/40 rounded-lg p-3 border border-scurry-foam max-h-48 overflow-y-auto">
            <div className="text-sm text-scurry-espresso whitespace-pre-wrap font-mono text-xs">
              {typeof transcript === 'string' ? transcript.slice(0, 2000) + (transcript.length > 2000 ? '...' : '') : JSON.stringify(transcript, null, 2)}
            </div>
          </div>
        </details>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Text Generation result view - extraction points and summary
const TextGenerationResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const summary = results.summary;
  const extractedInfo = results.extracted_information;
  const extractionPoints = results.extraction_points;
  const variables = results.variables_extracted;
  const [summaryExpanded, setSummaryExpanded] = useState(false);

  const internalKeys = new Set(['summary', 'extracted_information', 'extraction_points', 'variables_extracted', 'model_used', 'transcript_length', 'extraction_timestamp', 'participants']);
  const otherFields = Object.entries(results).filter(([k]) => !internalKeys.has(k));

  const summaryText = summary ? String(summary) : '';
  const summaryIsLong = summaryText.length > 800;

  return (
    <div className="space-y-3">
      {/* Summary */}
      {summaryText && (
        <div className="bg-scurry-foam/60 rounded-lg p-3 border border-scurry-foam">
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" />
            Generated Summary
          </div>
          <div className={`text-sm text-scurry-espresso prose prose-sm max-w-none prose-headings:text-scurry-espresso prose-headings:font-semibold prose-h1:text-base prose-h2:text-sm prose-h3:text-sm prose-p:my-2 prose-ul:my-1 prose-li:my-0.5 prose-strong:text-scurry-espresso prose-hr:my-3 ${!summaryExpanded && summaryIsLong ? 'max-h-96 overflow-hidden relative' : ''}`}>
            <Markdown>{summaryText}</Markdown>
            {!summaryExpanded && summaryIsLong && (
              <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-scurry-foam/95 to-transparent" />
            )}
          </div>
          {summaryIsLong && (
            <button
              onClick={() => setSummaryExpanded(!summaryExpanded)}
              className="mt-2 text-xs font-medium text-scurry-orange hover:text-scurry-orange-hover flex items-center gap-1"
            >
              {summaryExpanded ? <><ChevronUp className="h-3 w-3" /> Show less</> : <><ChevronDown className="h-3 w-3" /> Show full summary</>}
            </button>
          )}
        </div>
      )}

      {/* Extracted Information */}
      {extractedInfo && typeof extractedInfo === 'object' && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <Hash className="h-3.5 w-3.5" />
            Extracted Information
          </div>
          <div className="grid gap-2">
            {Object.entries(extractedInfo).map(([key, value]) => (
              <div key={key} className="bg-white border border-scurry-foam rounded-lg px-3 py-2">
                <span className="text-xs font-semibold text-scurry-orange uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
                <div className="text-sm text-scurry-espresso mt-0.5"><RenderValue value={value} /></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Extraction Points */}
      {extractionPoints && Array.isArray(extractionPoints) && extractionPoints.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-1.5">Extraction Points</div>
          <div className="flex flex-wrap gap-1.5">
            {extractionPoints.map((point: any, i: number) => (
              <span key={i} className="text-xs bg-scurry-orange/10 text-scurry-orange px-2 py-0.5 rounded-full font-medium">
                {typeof point === 'object' ? (point.name || JSON.stringify(point)) : String(point)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Variables */}
      {variables && (Array.isArray(variables) ? variables.length > 0 : Object.keys(variables).length > 0) && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-1.5">Variables Extracted</div>
          <ul className="space-y-0.5">
            {(Array.isArray(variables) ? variables : Object.keys(variables)).map((name: string, i: number) => (
              <li key={i} className="flex items-center gap-2 text-sm text-scurry-espresso">
                <span className="text-scurry-orange text-[6px]">●</span>
                {name}
              </li>
            ))}
          </ul>
        </div>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Conditional Logic result view - evaluation table with pass/fail indicators
const ConditionalLogicResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const pipelineContinues = results.pipeline_continues;
  const action = results.action;
  const message = results.message;
  const evaluationResults = results.evaluation_results;
  const crmData = results.crm_data;

  const knownKeys = new Set(['pipeline_continues', 'action', 'message', 'evaluation_results', 'crm_data']);
  const otherFields = Object.entries(results).filter(([k]) => !knownKeys.has(k));

  return (
    <div className="space-y-3">
      {/* Verdict */}
      <div className={`flex items-center gap-3 p-3 rounded-lg border ${
        pipelineContinues ? 'bg-green-50 border-green-200' : 'bg-amber-50 border-amber-200'
      }`}>
        <GitBranch className={`h-6 w-6 ${pipelineContinues ? 'text-green-600' : 'text-amber-600'}`} />
        <div>
          <div className={`text-sm font-bold ${pipelineContinues ? 'text-green-800' : 'text-amber-800'}`}>
            {pipelineContinues ? 'Pipeline Continues' : 'Pipeline Stopped'}
          </div>
          {action && <div className="text-xs text-scurry-latte mt-0.5">Action: {action}</div>}
          {message && <div className="text-xs text-scurry-latte mt-0.5">{message}</div>}
        </div>
      </div>

      {/* Evaluation Results */}
      {evaluationResults && Array.isArray(evaluationResults) && evaluationResults.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2">Condition Groups</div>
          <div className="space-y-2">
            {evaluationResults.map((group: any, gi: number) => (
              <div key={gi} className="bg-white border border-scurry-foam rounded-lg p-3">
                {group.group_name && (
                  <div className="text-xs font-semibold text-scurry-espresso mb-2">{group.group_name}</div>
                )}
                {group.conditions && Array.isArray(group.conditions) && (
                  <div className="space-y-1">
                    {group.conditions.map((cond: any, ci: number) => (
                      <div key={ci} className="flex items-center gap-2 text-sm">
                        <span className={`h-2 w-2 rounded-full flex-shrink-0 ${cond.result || cond.passes ? 'bg-green-500' : 'bg-red-500'}`} />
                        <span className="text-scurry-espresso">
                          {cond.field || cond.name || `Condition ${ci + 1}`}
                        </span>
                        {cond.operator && (
                          <span className="text-xs text-scurry-latte font-mono">{cond.operator}</span>
                        )}
                        {cond.value !== undefined && (
                          <span className="text-xs text-scurry-latte">"{String(cond.value)}"</span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {group.result !== undefined && (
                  <div className={`text-xs font-semibold mt-2 pt-1.5 border-t border-scurry-foam ${group.result ? 'text-green-600' : 'text-red-600'}`}>
                    Group: {group.result ? 'PASS' : 'FAIL'}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CRM Data preview */}
      {crmData && typeof crmData === 'object' && Object.keys(crmData).length > 0 && (
        <details className="group">
          <summary className="text-xs font-semibold text-scurry-latte uppercase tracking-wide cursor-pointer hover:text-scurry-espresso">
            CRM Data ▸
          </summary>
          <div className="mt-2 bg-scurry-foam/40 rounded-lg p-3 border border-scurry-foam">
            <RenderValue value={crmData} />
          </div>
        </details>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Action result view - CRM action with mapped fields
const ActionResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const system = results.system;
  const action = results.action;
  const result = results.result;
  const mappedFields = results.mapped_fields;

  const knownKeys = new Set(['system', 'action', 'result', 'mapped_fields']);
  const otherFields = Object.entries(results).filter(([k]) => !knownKeys.has(k));

  return (
    <div className="space-y-3">
      {/* Action header */}
      {(system || action) && (
        <div className="flex items-center gap-2 p-3 bg-scurry-foam/60 rounded-lg border border-scurry-foam">
          <Zap className="h-5 w-5 text-scurry-orange flex-shrink-0" />
          <div>
            <div className="text-sm font-medium text-scurry-espresso">
              {action && <span>{String(action)}</span>}
            </div>
            {system && <div className="text-xs text-scurry-latte">System: {String(system)}</div>}
          </div>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-white border border-scurry-foam rounded-lg p-3">
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-1.5">Result</div>
          <RenderValue value={result} />
        </div>
      )}

      {/* Mapped Fields */}
      {mappedFields && typeof mappedFields === 'object' && Object.keys(mappedFields).length > 0 && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2">Mapped Fields</div>
          <div className="grid gap-1.5">
            {Object.entries(mappedFields).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2 text-sm bg-scurry-foam/40 rounded px-3 py-1.5">
                <span className="font-medium text-scurry-espresso min-w-0 truncate">{key.replace(/_/g, ' ')}</span>
                <ArrowRight className="h-3 w-3 text-scurry-latte flex-shrink-0" />
                <span className="text-scurry-espresso truncate">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Company Name Matcher result view
const CompanyMatcherResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const orgId = results.organization_id;
  const orgName = results.organization_name;
  const persons = results.persons_created;
  const confidence = results.match_confidence;
  const reasoning = results.match_reasoning;

  const knownKeys = new Set(['organization_id', 'organization_name', 'persons_created', 'match_confidence', 'match_reasoning']);
  const otherFields = Object.entries(results).filter(([k]) => !knownKeys.has(k));

  return (
    <div className="space-y-3">
      {/* Organization match */}
      {orgName && (
        <div className="flex items-center gap-3 p-3 bg-scurry-foam/60 rounded-lg border border-scurry-foam">
          <Building2 className="h-5 w-5 text-scurry-orange flex-shrink-0" />
          <div className="min-w-0">
            <div className="text-sm font-medium text-scurry-espresso truncate">{orgName}</div>
            {orgId && <div className="text-xs text-scurry-latte">ID: {orgId}</div>}
          </div>
          {confidence && (
            <span className={`ml-auto text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${
              confidence === 'high' ? 'bg-green-100 text-green-700' :
              confidence === 'medium' ? 'bg-amber-100 text-amber-700' :
              'bg-red-100 text-red-700'
            }`}>
              {String(confidence)} confidence
            </span>
          )}
        </div>
      )}

      {/* Match reasoning */}
      {reasoning && (
        <div className="bg-white border border-scurry-foam rounded-lg p-3">
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-1.5">Match Reasoning</div>
          <div className="text-sm text-scurry-espresso">{String(reasoning)}</div>
        </div>
      )}

      {/* Persons Created */}
      {persons && Array.isArray(persons) && persons.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-scurry-latte uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5" />
            Persons Created ({persons.length})
          </div>
          <div className="space-y-1.5">
            {persons.map((person: any, i: number) => (
              <div key={i} className="flex items-center gap-2 text-sm bg-scurry-foam/40 rounded px-3 py-1.5">
                <User className="h-3.5 w-3.5 text-scurry-latte flex-shrink-0" />
                <span className="text-scurry-espresso">
                  {person.name || person.email || JSON.stringify(person)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Advanced Action result view - deal updates
const AdvancedActionResultView: React.FC<{ results: Record<string, any> }> = ({ results }) => {
  const dealId = results.deal_id;
  const fieldUpdated = results.field_updated;
  const newValue = results.new_value;
  const message = results.message;

  const knownKeys = new Set(['deal_id', 'field_updated', 'new_value', 'message']);
  const otherFields = Object.entries(results).filter(([k]) => !knownKeys.has(k));

  return (
    <div className="space-y-3">
      {/* Action summary */}
      <div className="flex items-center gap-3 p-3 bg-scurry-foam/60 rounded-lg border border-scurry-foam">
        <Zap className="h-5 w-5 text-scurry-orange flex-shrink-0" />
        <div className="min-w-0">
          {fieldUpdated && (
            <div className="text-sm font-medium text-scurry-espresso">
              Updated: {String(fieldUpdated).replace(/_/g, ' ')}
            </div>
          )}
          {dealId && <div className="text-xs text-scurry-latte">Deal ID: {dealId}</div>}
        </div>
      </div>

      {/* New value */}
      {newValue !== undefined && (
        <div className="bg-white border border-scurry-foam rounded-lg px-3 py-2">
          <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">New Value: </span>
          <span className="text-sm text-scurry-espresso font-medium">{String(newValue)}</span>
        </div>
      )}

      {/* Message */}
      {message && (
        <div className="text-sm text-scurry-espresso bg-scurry-foam/40 rounded-lg px-3 py-2">{String(message)}</div>
      )}

      {otherFields.length > 0 && (
        <div className="border-t border-scurry-foam pt-2 space-y-2">
          {otherFields.map(([key, value]) => (
            <div key={key} className="border-b border-scurry-foam/50 pb-1.5 last:border-0">
              <span className="text-xs font-semibold text-scurry-latte uppercase tracking-wide">{key.replace(/_/g, ' ')}</span>
              <div className="mt-0.5"><RenderValue value={value} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Dispatcher: picks the right view based on component type and result shape
const FormattedResultView: React.FC<{ results: Record<string, any>; componentType: string }> = ({ results: rawResults, componentType }) => {
  // Unwrap nested {status, data} structure from execution engine
  const results = (rawResults.data && typeof rawResults.data === 'object' && ('email_body' in rawResults.data || 'email_subject' in rawResults.data || 'summary' in rawResults.data || 'extracted_information' in rawResults.data || 'passes_filter' in rawResults.data || 'transcript' in rawResults.data || 'pipeline_continues' in rawResults.data || 'organization_name' in rawResults.data || 'mapped_fields' in rawResults.data))
    ? rawResults.data
    : rawResults;

  // Duck-typing detection as fallback when componentType doesn't match
  if (componentType === 'email' || 'email_subject' in results || 'email_body' in results) {
    if ('email_subject' in results || 'email_body' in results) return <EmailResultView results={results} />;
  }
  if (componentType === 'ai_filter' || 'passes_filter' in results) {
    if ('passes_filter' in results) return <AIFilterResultView results={results} />;
  }
  if (componentType === 'input_sources' || ('transcript' in results && 'participants' in results)) {
    if ('transcript' in results || 'meeting_title' in results) return <InputSourcesResultView results={results} />;
  }
  if (componentType === 'text_generation' || ('extracted_information' in results || 'extraction_points' in results)) {
    if ('extracted_information' in results || 'extraction_points' in results || ('summary' in results && 'variables_extracted' in results)) return <TextGenerationResultView results={results} />;
  }
  if (componentType === 'conditional_logic' || 'pipeline_continues' in results) {
    if ('pipeline_continues' in results || 'evaluation_results' in results) return <ConditionalLogicResultView results={results} />;
  }
  if (componentType === 'company_name_matcher' || 'organization_name' in results) {
    if ('organization_name' in results || 'match_confidence' in results) return <CompanyMatcherResultView results={results} />;
  }
  if (componentType === 'advanced_action' || ('deal_id' in results && 'field_updated' in results)) {
    return <AdvancedActionResultView results={results} />;
  }
  if (componentType === 'action' || ('system' in results && 'mapped_fields' in results)) {
    if ('mapped_fields' in results) return <ActionResultView results={results} />;
  }

  // Fallback: generic key-value view
  return (
    <div className="space-y-3">
      {Object.entries(results).map(([key, value]) => (
        <div key={key} className="border-b border-scurry-foam pb-2 last:border-0">
          <span className="text-xs font-semibold text-scurry-orange uppercase tracking-wide">
            {key.replace(/_/g, ' ')}
          </span>
          <div className="text-sm text-scurry-espresso mt-1">
            <RenderValue value={value} />
          </div>
        </div>
      ))}
    </div>
  );
};

const ComponentTestUI: React.FC<ComponentTestUIProps> = ({
  workflowId,
  componentId,
  componentType,
}) => {
  const {
    testResults,
    testResultTimestamp,
    selectedTranscriptId,
    setTestResults,
    setSelectedTranscriptId,
  } = useComponentTestResults(workflowId, componentId);

  const { refreshAcorns } = useAuth();
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<'formatted' | 'json'>('formatted');
  const [transcriptSearch, setTranscriptSearch] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const { toast } = useToast();

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [dropdownOpen]);

  // Auto-focus search when dropdown opens
  useEffect(() => {
    if (dropdownOpen) {
      setTimeout(() => searchInputRef.current?.focus(), 0);
    }
  }, [dropdownOpen]);

  // Fetch Fireflies transcripts
  const { data: transcripts, isLoading: transcriptsLoading } = useQuery({
    queryKey: ["fireflies-transcripts"],
    queryFn: () => firefliesApi.listTranscripts().then((res) => res.data),
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Fetch demo transcripts (always available)
  const { data: demoTranscripts } = useQuery({
    queryKey: ["demo-transcripts"],
    queryFn: () => demoTranscriptsApi.list().then((res) => res.data),
    staleTime: 60 * 60 * 1000, // 1 hour — these don't change
  });

  // Merge demo transcripts into the same list as Fireflies transcripts
  const allTranscripts = useMemo(() => {
    const demos: FirefliesTranscriptSummary[] = (demoTranscripts || []).map((d: any) => ({
      id: d.id,
      title: `[Demo] ${d.title}`,
      date: undefined,
      duration: d.duration,
      participant_count: d.participants.length,
    }));
    const fireflies: FirefliesTranscriptSummary[] = transcripts || [];
    return [...demos, ...fireflies];
  }, [transcripts, demoTranscripts]);

  // Filter transcripts based on search
  const filteredTranscripts = useMemo(() => {
    if (!allTranscripts.length) return [];
    if (!transcriptSearch.trim()) return allTranscripts;
    const search = transcriptSearch.toLowerCase();
    return allTranscripts.filter((t: FirefliesTranscriptSummary) =>
      t.title.toLowerCase().includes(search)
    );
  }, [allTranscripts, transcriptSearch]);

  // Test component mutation. withTrace=true asks the backend to capture a
  // per-call API trace and return it in the response (issue #184).
  const testMutation = useMutation({
    mutationFn: async (vars: { transcriptId?: string; withTrace?: boolean }) => {
      const { transcriptId, withTrace } = vars;
      const options = withTrace ? { trace: true } : undefined;
      if (transcriptId?.startsWith("demo_")) {
        const res = await demoTranscriptsApi.get(transcriptId);
        const demo = res.data;
        return componentApi.test(componentId, {
          test_data: {
            source: "fireflies_webhook",
            transcript: demo.transcript,
            meeting_title: demo.meeting_title,
            participants: demo.participants,
            participant_emails: demo.participant_emails,
            organizer_email: demo.organizer_email,
            recipient_email: demo.recipient_email,
            duration: demo.duration * 60,
          },
        }, options);
      }
      const payload = transcriptId
        ? { fireflies_transcript_id: transcriptId }
        : undefined;
      return componentApi.test(componentId, payload, options);
    },
    onSuccess: (data) => {
      setTestResults({ testResults: data.data });
      refreshAcorns();
      if (data.data.success) {
        toast({
          title: "Test Successful",
          description: "Component executed successfully",
        });
      } else {
        toast({
          title: "Test Failed",
          description: data.data.error || "Component test failed",
          variant: "destructive",
        });
      }
    },
    onError: (error: any) => {
      toast({
        title: "Test Error",
        description: error.response?.data?.detail || "Failed to run test",
        variant: "destructive",
      });
    },
  });

  const handleRunTest = () => {
    const transcriptId =
      selectedTranscriptId && selectedTranscriptId !== "__default__"
        ? selectedTranscriptId
        : undefined;
    testMutation.mutate({ transcriptId, withTrace: false });
  };

  const handleRunTestWithData = () => {
    const transcriptId =
      selectedTranscriptId && selectedTranscriptId !== "__default__"
        ? selectedTranscriptId
        : undefined;
    testMutation.mutate({ transcriptId, withTrace: true });
  };

  const handleTranscriptSelect = (value: string) => {
    setSelectedTranscriptId(value);
    setTranscriptSearch('');
    setDropdownOpen(false);
  };

  const copyToClipboard = () => {
    if (testResults) {
      navigator.clipboard.writeText(JSON.stringify(testResults, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const downloadResults = () => {
    if (testResults) {
      const dataStr = JSON.stringify(testResults, null, 2);
      const dataBlob = new Blob([dataStr], { type: "application/json" });
      const url = URL.createObjectURL(dataBlob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `test-results-${componentId}-${Date.now()}.json`;
      link.click();
      URL.revokeObjectURL(url);
    }
  };

  const formatDuration = (minutes: number) => {
    return `${Math.floor(minutes)} min`;
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <Card className="border-scurry-foam">
      <CardHeader className="bg-scurry-foam/40 border-b border-scurry-foam">
        <CardTitle className="text-base font-semibold flex items-center text-scurry-espresso">
          <Play className="h-5 w-5 mr-2 text-scurry-orange" />
          Test Component
        </CardTitle>
        <p className="text-xs text-scurry-latte mt-1">Let's make sure your extraction is working perfectly! 🧪</p>
      </CardHeader>
      <CardContent className="space-y-4 pt-4">
        {/* Transcript Selection */}
        <div className="space-y-2">
          <Label className="text-scurry-espresso font-medium">Select Test Data</Label>
          {transcriptsLoading ? (
            <div className="flex items-center justify-center p-4">
              <LoadingSpinner size="sm" />
              <span className="ml-2 text-sm text-scurry-latte">
                Loading transcripts...
              </span>
            </div>
          ) : (transcripts && transcripts.length > 0) || (demoTranscripts && demoTranscripts.length > 0) ? (
            <div className="relative" ref={dropdownRef}>
              {/* Trigger button */}
              <button
                type="button"
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex h-10 w-full items-center justify-between rounded-md border border-scurry-latte/25 bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
              >
                <span className={`truncate ${!selectedTranscriptId || selectedTranscriptId === '__default__' ? 'text-muted-foreground' : ''}`}>
                  {(() => {
                    if (!selectedTranscriptId || selectedTranscriptId === '__default__') return 'Use default mock data';
                    if (selectedTranscriptId.startsWith('demo_')) {
                      const d = demoTranscripts?.find((dt: any) => dt.id === selectedTranscriptId);
                      return d ? `${d.title}` : 'Use default mock data';
                    }
                    const t = transcripts?.find((tr: FirefliesTranscriptSummary) => tr.id === selectedTranscriptId);
                    return t ? t.title : 'Use default mock data';
                  })()}
                </span>
                <ChevronDown className={`h-4 w-4 opacity-50 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {/* Dropdown panel */}
              {dropdownOpen && (
                <div className="absolute z-50 mt-1 w-full rounded-md border bg-popover text-popover-foreground shadow-md animate-in fade-in-0 zoom-in-95">
                  {/* Embedded search */}
                  <div className="p-2 border-b border-scurry-foam">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-scurry-latte" />
                      <input
                        ref={searchInputRef}
                        type="text"
                        placeholder="Search transcripts..."
                        value={transcriptSearch}
                        onChange={(e) => setTranscriptSearch(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 text-sm border border-scurry-latte/25 rounded-md bg-background outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                      />
                    </div>
                  </div>

                  {/* Options list */}
                  <div className="max-h-60 overflow-y-auto p-1">
                    <button
                      type="button"
                      onClick={() => handleTranscriptSelect('__default__')}
                      className={`relative flex w-full items-center rounded-sm px-3 py-2 text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground ${
                        (!selectedTranscriptId || selectedTranscriptId === '__default__') ? 'bg-accent/50' : ''
                      }`}
                    >
                      {(!selectedTranscriptId || selectedTranscriptId === '__default__') && (
                        <Check className="h-3.5 w-3.5 mr-2 text-scurry-orange flex-shrink-0" />
                      )}
                      <span className={(!selectedTranscriptId || selectedTranscriptId === '__default__') ? '' : 'ml-5.5'}>
                        Default Mock Data
                      </span>
                    </button>
                    {filteredTranscripts.map((transcript: FirefliesTranscriptSummary) => (
                      <button
                        type="button"
                        key={transcript.id}
                        onClick={() => handleTranscriptSelect(transcript.id)}
                        className={`relative flex w-full items-start rounded-sm px-3 py-2 text-sm cursor-pointer hover:bg-accent hover:text-accent-foreground ${
                          selectedTranscriptId === transcript.id ? 'bg-accent/50' : ''
                        }`}
                      >
                        {selectedTranscriptId === transcript.id && (
                          <Check className="h-3.5 w-3.5 mr-2 mt-0.5 text-scurry-orange flex-shrink-0" />
                        )}
                        <div className={selectedTranscriptId === transcript.id ? '' : 'ml-[22px]'}>
                          <span className="font-medium">{transcript.title}</span>
                          <div className="text-xs text-scurry-latte">
                            {formatDate(transcript.date)} •{" "}
                            {formatDuration(transcript.duration)} •{" "}
                            {transcript.participant_count} participants
                          </div>
                        </div>
                      </button>
                    ))}
                    {filteredTranscripts.length === 0 && transcriptSearch && (
                      <div className="text-sm text-scurry-latte p-3 text-center">
                        No transcripts match "{transcriptSearch}"
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-scurry-latte p-3 bg-scurry-foam rounded-lg border border-scurry-latte/25">
              No transcripts available. Add your Fireflies API key in
              Settings to load transcripts.
            </div>
          )}
        </div>

        {/* Run Test Buttons. "Run Test with Data" runs the same code path
            with trace=true so each outbound API call (RAG, Anthropic,
            OpenAI, Fireflies, Pipedrive, SMTP) is captured for inspection. */}
        <div className="flex gap-2">
          <Button
            onClick={handleRunTest}
            disabled={testMutation.isPending}
            className="flex-1 bg-gradient-to-br from-scurry-orange to-scurry-orange-hover hover:from-scurry-orange-hover hover:to-scurry-orange-hover text-white font-semibold rounded-lg shadow-lg shadow-scurry-orange/25"
          >
            {testMutation.isPending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Running Test...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Run Test
              </>
            )}
          </Button>
          <Button
            onClick={handleRunTestWithData}
            disabled={testMutation.isPending}
            variant="outline"
            className="flex-1 border-scurry-orange text-scurry-orange hover:bg-scurry-orange/10 font-semibold rounded-lg"
            title="Run the test and capture the full API call history (RAG retrievals, Anthropic prompts, embeddings, integrations)."
          >
            {testMutation.isPending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Activity className="h-4 w-4 mr-2" />
                Run Test with Data
              </>
            )}
          </Button>
        </div>

        {/* Test Results */}
        {testResults && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Label className="text-scurry-espresso font-medium">Test Results</Label>
                {testResultTimestamp && (
                  <span className="text-xs text-scurry-latte">
                    Last tested: {new Date(testResultTimestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {new Date(testResultTimestamp).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-2">
                {/* Formatted/JSON Toggle */}
                <div className="flex border border-scurry-gray-border rounded-lg overflow-hidden">
                  <button
                    onClick={() => setViewMode('formatted')}
                    className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1 transition-all ${
                      viewMode === 'formatted'
                        ? 'text-scurry-orange bg-white'
                        : 'text-scurry-latte bg-scurry-gray-light hover:bg-scurry-foam'
                    }`}
                  >
                    <FileText className="h-3.5 w-3.5" />
                    Formatted
                  </button>
                  <button
                    onClick={() => setViewMode('json')}
                    className={`px-3 py-1.5 text-xs font-semibold flex items-center gap-1 border-l border-scurry-gray-border transition-all ${
                      viewMode === 'json'
                        ? 'text-scurry-orange bg-white'
                        : 'text-scurry-latte bg-scurry-gray-light hover:bg-scurry-foam'
                    }`}
                  >
                    <FileCode className="h-3.5 w-3.5" />
                    JSON
                  </button>
                </div>
                <Button variant="outline" size="sm" onClick={copyToClipboard} className="border-scurry-latte/25 text-scurry-espresso">
                  {copied ? (
                    <Check className="h-3 w-3 mr-1 text-scurry-green" />
                  ) : (
                    <Copy className="h-3 w-3 mr-1" />
                  )}
                  {copied ? "Copied" : "Copy"}
                </Button>
                <Button variant="outline" size="sm" onClick={downloadResults} className="border-scurry-latte/25 text-scurry-espresso">
                  <Download className="h-3 w-3 mr-1" />
                  Download
                </Button>
              </div>
            </div>

            {testResults.success ? (
              <div className="bg-scurry-green-light border border-scurry-green/30 rounded-xl p-4">
                {/* Metadata bar */}
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-2">
                    <Check className="h-5 w-5 text-scurry-green" />
                    <span className="font-semibold text-scurry-green">
                      Test Executed
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs bg-scurry-foam text-scurry-espresso px-2 py-0.5 rounded-full font-medium">
                      {componentType.replace(/_/g, ' ')}
                    </span>
                    <span className="text-sm text-scurry-latte">
                      🎉
                    </span>
                  </div>
                </div>
                <div className="bg-white border border-scurry-foam rounded-lg p-4 max-h-96 overflow-y-auto">
                  {viewMode === 'formatted' && testResults.results ? (
                    <FormattedResultView results={testResults.results} componentType={componentType} />
                  ) : (
                    <pre className="text-sm text-scurry-espresso whitespace-pre-wrap font-mono">
                      {JSON.stringify(testResults.results, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-scurry-red-light border border-scurry-red/20 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-2">
                    <Play className="h-5 w-5 text-scurry-red" />
                    <span className="font-semibold text-scurry-red">Oops, something went wrong! 🐿️</span>
                  </div>
                  <span className="text-xs bg-scurry-red-light text-scurry-red px-2 py-0.5 rounded-full font-medium">
                    Failed
                  </span>
                </div>
                <p className="text-sm text-scurry-red mb-3">{testResults.error}</p>
                {testResults.results && (
                  <div className="bg-white border border-scurry-foam rounded-lg p-4 max-h-96 overflow-y-auto">
                    <pre className="text-sm text-scurry-espresso whitespace-pre-wrap font-mono">
                      {JSON.stringify(testResults.results, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* RAG-focused panel — status badge, diagnostics, and per-call chunk breakdown.
            Shown above the generic API Call History so users can answer
            "did RAG work?" / "why didn't it fire?" without scanning every API call. */}
        {testResults?.trace && Array.isArray(testResults.trace) && (
          <div className="mb-3">
            <RagPanel trace={testResults.trace as RagTraceEntry[]} />
          </div>
        )}

        {/* API Call History — only present when "Run Test with Data" was used */}
        {testResults?.trace && Array.isArray(testResults.trace) && (
          <ApiCallHistoryPanel entries={testResults.trace as TraceEntry[]} />
        )}
      </CardContent>
    </Card>
  );
};

// ============================================================================
// API Call History panel (issue #184)
// ============================================================================

// Color hints by family — labels themselves are derived from the trace type
// so we don't repeat the model brand ("Sonnet"/"Haiku") on every row. The
// actual model id is in entry.request.model when expanded.
const TRACE_TYPE_COLORS: Array<{ prefix: string; color: string }> = [
  { prefix: "rag.", color: "bg-purple-100 text-purple-800" },
  { prefix: "openai.", color: "bg-emerald-100 text-emerald-800" },
  { prefix: "anthropic.haiku", color: "bg-amber-100 text-amber-800" },
  { prefix: "anthropic.sonnet", color: "bg-orange-100 text-orange-800" },
  { prefix: "anthropic.", color: "bg-amber-100 text-amber-800" },
  { prefix: "fireflies.", color: "bg-sky-100 text-sky-800" },
  { prefix: "pipedrive.", color: "bg-indigo-100 text-indigo-800" },
  { prefix: "smtp.", color: "bg-rose-100 text-rose-800" },
];

function getTypeLabel(type: string): { label: string; color: string } {
  const match = TRACE_TYPE_COLORS.find((c) => type.startsWith(c.prefix));
  return { label: type, color: match?.color ?? "bg-scurry-foam text-scurry-espresso" };
}

const ApiCallHistoryPanel: React.FC<{ entries: TraceEntry[] }> = ({ entries }) => {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const toggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (entries.length === 0) {
    return (
      <div className="space-y-2">
        <Label className="text-scurry-espresso font-medium flex items-center gap-2">
          <Activity className="h-4 w-4" /> API Call History
        </Label>
        <div className="text-sm text-scurry-latte p-3 bg-scurry-foam rounded-lg border border-scurry-latte/25">
          No outbound API calls were captured for this test run.
        </div>
      </div>
    );
  }

  const totalDuration = entries.reduce((sum, e) => sum + (e.duration_ms || 0), 0);
  const errorCount = entries.filter((e) => e.error).length;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-scurry-espresso font-medium flex items-center gap-2">
          <Activity className="h-4 w-4" /> API Call History
          <span className="text-xs font-normal text-scurry-latte">
            ({entries.length} call{entries.length === 1 ? "" : "s"} · {totalDuration.toFixed(0)}ms total
            {errorCount > 0 && ` · ${errorCount} error${errorCount === 1 ? "" : "s"}`})
          </span>
        </Label>
      </div>
      <div className="space-y-1.5">
        {entries.map((entry, idx) => {
          const expanded = expandedIds.has(entry.id);
          const { label, color } = getTypeLabel(entry.type);
          return (
            <div
              key={entry.id}
              className={`border rounded-lg overflow-hidden ${entry.error ? "border-scurry-red/40 bg-scurry-red-light/30" : "border-scurry-gray-border bg-white"}`}
            >
              <button
                onClick={() => toggle(entry.id)}
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-scurry-foam/50 transition-colors text-left"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="text-xs font-mono text-scurry-latte w-6 text-right">{idx + 1}.</span>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded ${color}`}>{label}</span>
                  {entry.error && (
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-scurry-red-light text-scurry-red flex items-center gap-1">
                      <AlertCircle className="h-3 w-3" /> Error
                    </span>
                  )}
                  {entry.metadata?.model && (
                    <span className="text-xs text-scurry-latte truncate">{String(entry.metadata.model)}</span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-scurry-latte flex-shrink-0">
                  <span>{entry.duration_ms.toFixed(0)}ms</span>
                  {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </div>
              </button>
              {expanded && (
                <div className="px-3 py-2 border-t border-scurry-gray-border bg-scurry-gray-light/40 space-y-2">
                  <div className="text-xs text-scurry-latte">
                    Started: {new Date(entry.started_at).toLocaleTimeString()} · Duration: {entry.duration_ms.toFixed(2)}ms
                  </div>
                  {entry.error && (
                    <div className="bg-scurry-red-light text-scurry-red text-xs p-2 rounded font-mono whitespace-pre-wrap">
                      {entry.error}
                    </div>
                  )}
                  {entry.request && (
                    <div>
                      <div className="text-xs font-semibold text-scurry-espresso mb-1">Request</div>
                      <pre className="text-xs bg-white border border-scurry-gray-border rounded p-2 max-h-72 overflow-auto whitespace-pre-wrap font-mono">
                        {JSON.stringify(entry.request, null, 2)}
                      </pre>
                    </div>
                  )}
                  {entry.response && (
                    <div>
                      <div className="text-xs font-semibold text-scurry-espresso mb-1">Response</div>
                      <pre className="text-xs bg-white border border-scurry-gray-border rounded p-2 max-h-72 overflow-auto whitespace-pre-wrap font-mono">
                        {JSON.stringify(entry.response, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ComponentTestUI;
