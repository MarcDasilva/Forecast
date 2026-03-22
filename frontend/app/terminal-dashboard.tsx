"use client";

import { ForecastPanel, type CategoryForecastResponse } from "@/components/forecast-panel";
import Dither from "@/components/Dither";
import { useCallback, useEffect, useMemo, useState } from "react";

type ScoresResponse = {
  scores: Record<string, number>;
  dataset_count: number;
  last_updated: string | null;
};

type SpecialistScore = {
  id: string;
  category: string;
  agent_name: string;
  score: number;
  status_label: string;
  confidence: number;
  rationale: string;
  benchmark_highlights: string[];
  recommendations: string[];
  supporting_evidence: string[];
  source_dataset_ids: string[];
  created_at: string | null;
};

type SpecialistScoresResponse = {
  scores: Record<string, SpecialistScore | null>;
  last_updated: string | null;
};

type DatasetListItem = {
  id: string;
  source_ref: string;
  input_type: string;
  status: string;
  created_at: string | null;
};

type DatasetListResponse = {
  page: number;
  page_size: number;
  total: number;
  items: DatasetListItem[];
};

type RelevantDatasetItem = {
  id: string;
  source_ref: string;
  input_type: string;
  created_at: string | null;
  title: string | null;
  geography: string | null;
  time_period: string | null;
  final_score: number;
  benchmark_eval: number;
  similarity: number;
};

type RelevantDatasetsResponse = {
  category: string;
  items: RelevantDatasetItem[];
};

type DatasetScoreDetail = {
  final_score: number;
  similarity: number;
  benchmark_eval: number;
};

type DatasetDetailResponse = {
  id: string;
  source_ref: string;
  status: string;
  input_type: string;
  summary: {
    title?: string;
    geography?: string;
    time_period?: string;
    civic_relevance?: string;
    data_quality_notes?: string;
    key_metrics?: Record<string, number | null>;
  } | null;
  error_msg: string | null;
  scores: Record<string, DatasetScoreDetail>;
};

type RunSpecialistResponse = {
  result: SpecialistScore;
};

type RunAllSpecialistsResponse = {
  results: SpecialistScore[];
};

type ChatHistoryItem = {
  role: "user" | "assistant";
  content: string;
  toolCalls?: { name?: string; result?: string }[];
  reasoningTrace?: AgentReasoningStep[];
  attachments?: ChatAttachment[];
};

type ChatAttachment = {
  artifact_id: string;
  dataset_id?: string | null;
  kind: string;
  label: string;
  filename: string;
  content_type: string;
  size_bytes?: number | null;
  download_url: string;
  source_ref?: string | null;
  created_at?: string | null;
};

type ScoreMetricComponent = {
  metric: string;
  label: string;
  raw_value: number;
  normalized_score: number;
  formula: string;
  interpretation: string;
};

type BenchmarkBreakdown = {
  category: string;
  benchmark_eval: number;
  metric_count: number;
  benchmark_formula: string;
  components: ScoreMetricComponent[];
};

type ScoreContributor = {
  dataset_id: string;
  source_ref: string;
  title: string | null;
  geography: string | null;
  time_period: string | null;
  created_at: string | null;
  final_score: number;
  similarity: number;
  benchmark_eval: number;
  contribution_weight: number;
  score_equation: string;
  benchmark_breakdown: BenchmarkBreakdown;
};

type CategoryScoreExplanation = {
  category: string;
  aggregated_score: number;
  dataset_count: number;
  importance_weight: number;
  importance_weight_used_in_final_score: boolean;
  scoring_formula: string;
  aggregation_formula: string;
  benchmark_formula: string;
  top_contributors: ScoreContributor[];
};

type AgentReasoningStep = {
  step: number;
  tool_name: string;
  title: string;
  summary: string;
  args: Record<string, unknown>;
  result_preview?: string | null;
  scoring_explanation?: CategoryScoreExplanation | null;
};

type AgentChatResponse = {
  response: string;
  tool_calls: { name?: string; result?: string }[];
  reasoning_trace: AgentReasoningStep[];
  attachments: ChatAttachment[];
};

type IngestResponse = {
  dataset_id: string;
  status: string;
  message: string;
};

type ProcessEntry = {
  id: string;
  tone: "info" | "success" | "warn";
  message: string;
  createdAt: string;
};

type TerminalViewMode = "intelligence" | "ingest";
type DatasourceMode = "endpoint" | "file" | "webscrape" | "transcript";
type ForecastMode = "time_to_target" | "required_rate";

const CATEGORY_ORDER = [
  "housing",
  "employment",
  "transportation",
  "healthcare",
  "placemaking",
] as const;

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

function resolveApiUrl(path: string) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const hasBody = init?.body !== undefined && init?.body !== null;

  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers,
    ...init,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Request failed for ${path}: ${response.status} ${text}`);
  }

  return (await response.json()) as T;
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) {
    return "--";
  }

  return new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function truncateMiddle(value: string, length = 48) {
  if (value.length <= length) {
    return value;
  }

  const head = Math.ceil(length * 0.62);
  const tail = Math.floor(length * 0.22);
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatCategoryLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDecimal(value: number | null | undefined, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }

  return value.toFixed(digits);
}

function formatFileSize(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value) || value <= 0) {
    return "--";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function getDefaultForecastTarget(score: number | null | undefined) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return "75";
  }

  const nextTarget = Math.max(55, Math.min(95, Math.ceil(score / 5) * 5 + 10));
  return nextTarget.toFixed(0);
}

function getDefaultForecastDate() {
  const base = new Date();
  base.setDate(base.getDate() + 180);
  return base.toISOString().slice(0, 10);
}

function dedupeRelevantSources(items: RelevantDatasetItem[]) {
  const seen = new Set<string>();

  return items.filter((item) => {
    const key = `${item.source_ref.trim().toLowerCase()}::${(item.title ?? "").trim().toLowerCase()}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function buildTerminalText(args: {
  scores: ScoresResponse | null;
  specialists: SpecialistScoresResponse | null;
  selectedCategory: string;
  selectedDataset: DatasetDetailResponse | null;
}) {
  const { scores, specialists, selectedCategory, selectedDataset } = args;
  const specialist = specialists?.scores[selectedCategory] ?? null;

  const lines = [
    "FORECAST // MUNICIPAL SIGNAL CONSOLE",
    "====================================",
    "",
    `API BASE      : ${API_BASE_URL}`,
    `DATASETS      : ${scores?.dataset_count ?? "--"}`,
    `LAST REFRESH  : ${formatTimestamp(specialists?.last_updated ?? scores?.last_updated)}`,
    "",
    "CATEGORY SCOREBOARD",
    "-------------------",
    ...CATEGORY_ORDER.map((category) => {
      const aggregate = scores?.scores[category];
      const specialistScore = specialists?.scores[category]?.score;
      const specialistBand = specialists?.scores[category]?.status_label ?? "NO RUN";
      return `${category.toUpperCase().padEnd(16)} agg=${String(
        aggregate?.toFixed?.(2) ?? "--",
      ).padStart(6)} | specialist=${String(specialistScore ?? "--").padStart(5)} | band=${specialistBand}`;
    }),
    "",
    `FOCUS CATEGORY : ${selectedCategory.toUpperCase()}`,
    `AGENT          : ${specialist?.agent_name ?? "--"}`,
    `BAND           : ${specialist?.status_label ?? "--"}`,
    `CONFIDENCE     : ${specialist ? `${Math.round(specialist.confidence * 100)}%` : "--"}`,
    "",
    "RATIONALE",
    "---------",
    specialist?.rationale ?? "No specialist assessment available.",
    "",
    "BENCHMARK HIGHLIGHTS",
    "--------------------",
    ...(specialist?.benchmark_highlights.length
      ? specialist.benchmark_highlights.map((item, index) => `${index + 1}. ${item}`)
      : ["No benchmark highlights available."]),
    "",
    "RECOMMENDATIONS",
    "---------------",
    ...(specialist?.recommendations.length
      ? specialist.recommendations.map((item, index) => `${index + 1}. ${item}`)
      : ["No recommendations available."]),
  ];

  if (!selectedDataset) {
    lines.push("", "SELECTED DATASET", "----------------", "No dataset selected.");
    return lines.join("\n");
  }

  const summary = selectedDataset.summary ?? {};
  const metrics = summary.key_metrics ?? {};

  lines.push(
    "",
    "SELECTED DATASET",
    "----------------",
    `ID            : ${selectedDataset.id}`,
    `SOURCE        : ${selectedDataset.source_ref}`,
    `TYPE          : ${selectedDataset.input_type}`,
    `STATUS        : ${selectedDataset.status}`,
    `TITLE         : ${summary.title ?? "--"}`,
    `GEOGRAPHY     : ${summary.geography ?? "--"}`,
    `TIME PERIOD   : ${summary.time_period ?? "--"}`,
    "",
    "METRICS",
    "-------",
    ...(Object.entries(metrics).length
      ? Object.entries(metrics).map(([key, value]) => `${key} = ${value ?? "null"}`)
      : ["No key metrics available."]),
  );

  return lines.join("\n");
}

export function TerminalDashboard() {
  const [scores, setScores] = useState<ScoresResponse | null>(null);
  const [specialists, setSpecialists] = useState<SpecialistScoresResponse | null>(null);
  const [datasets, setDatasets] = useState<DatasetListResponse | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("housing");
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [selectedDataset, setSelectedDataset] = useState<DatasetDetailResponse | null>(null);
  const [relevantSources, setRelevantSources] = useState<RelevantDatasetItem[]>([]);
  const [chatDraft, setChatDraft] = useState("");
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [processEntries, setProcessEntries] = useState<ProcessEntry[]>([]);
  const [showProcessPanel, setShowProcessPanel] = useState(false);
  const [terminalViewMode, setTerminalViewMode] = useState<TerminalViewMode>("intelligence");
  const [isChatWorkspaceOpen, setIsChatWorkspaceOpen] = useState(false);
  const [isSourceInspectorOpen, setIsSourceInspectorOpen] = useState(false);
  const [renameDraft, setRenameDraft] = useState("");
  const [isEditingInspectorName, setIsEditingInspectorName] = useState(false);
  const [isRenamingDataset, setIsRenamingDataset] = useState(false);
  const [datasourceMode, setDatasourceMode] = useState<DatasourceMode>("endpoint");
  const [datasourceUrl, setDatasourceUrl] = useState("");
  const [webscrapeUrl, setWebscrapeUrl] = useState("");
  const [transcriptText, setTranscriptText] = useState("");
  const [scrapeTargets, setScrapeTargets] = useState("");
  const [datasourceLabel, setDatasourceLabel] = useState("");
  const [datasourceFile, setDatasourceFile] = useState<File | null>(null);
  const [isSubmittingDatasource, setIsSubmittingDatasource] = useState(false);
  const [ingestDatasetId, setIngestDatasetId] = useState<string | null>(null);
  const [ingestResult, setIngestResult] = useState<DatasetDetailResponse | null>(null);
  const [ingestConsole, setIngestConsole] = useState(
    [
      "DATASOURCE INGEST CONSOLE",
      "=========================",
      "",
      "Paste an API endpoint, interview transcript,",
      "or attach a CSV file.",
      "The dataset will be ingested, summarized, embedded, scored,",
      "and stored in the backend, while progress is mirrored in the",
      "process window below.",
    ].join("\n"),
  );
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [runningCategory, setRunningCategory] = useState<string | null>(null);
  const [runningAllAgents, setRunningAllAgents] = useState(false);
  const [showForecastPanel, setShowForecastPanel] = useState(false);
  const [forecastMode, setForecastMode] = useState<ForecastMode>("time_to_target");
  const [forecastTargetY, setForecastTargetY] = useState("75");
  const [forecastTargetDate, setForecastTargetDate] = useState(getDefaultForecastDate);
  const [forecastPeriods, setForecastPeriods] = useState(365);
  const [forecastData, setForecastData] = useState<CategoryForecastResponse | null>(null);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [isForecastLoading, setIsForecastLoading] = useState(false);

  const appendProcessEntry = useCallback((message: string, tone: ProcessEntry["tone"] = "info") => {
    setShowProcessPanel(true);
    setProcessEntries((current) => [
      {
        id: crypto.randomUUID(),
        tone,
        message,
        createdAt: new Date().toISOString(),
      },
      ...current,
    ].slice(0, 60));
  }, []);

  const loadDashboardData = useCallback(async () => {
    setError(null);

    try {
      const [scoresPayload, specialistsPayload, datasetsPayload] = await Promise.all([
        fetchJson<ScoresResponse>("/scores"),
        fetchJson<SpecialistScoresResponse>("/specialist-scores"),
        fetchJson<DatasetListResponse>("/datasets?page=1&page_size=12"),
      ]);

      setScores(scoresPayload);
      setSpecialists(specialistsPayload);
      setDatasets(datasetsPayload);

      const firstDatasetId = datasetsPayload.items[0]?.id ?? null;
      setSelectedDatasetId((current) =>
        current && datasetsPayload.items.some((item) => item.id === current) ? current : firstDatasetId,
      );

      if (!specialistsPayload.scores[selectedCategory]) {
        const fallbackCategory = CATEGORY_ORDER.find(
          (category) => specialistsPayload.scores[category] !== null,
        );
        if (fallbackCategory) {
          setSelectedCategory(fallbackCategory);
        }
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unknown dashboard error.");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [selectedCategory]);

  useEffect(() => {
    void loadDashboardData();

    const interval = window.setInterval(() => {
      setIsRefreshing(true);
      void loadDashboardData();
    }, 30000);

    return () => window.clearInterval(interval);
  }, [loadDashboardData]);

  useEffect(() => {
    if (!selectedDatasetId) {
      setSelectedDataset(null);
      setRenameDraft("");
      return;
    }

    let active = true;

    async function loadDatasetDetail() {
      try {
        const payload = await fetchJson<DatasetDetailResponse>(`/datasets/${selectedDatasetId}`);
        if (active) {
          setSelectedDataset(payload);
        }
      } catch (detailError) {
        if (active) {
          setError(
            detailError instanceof Error ? detailError.message : "Failed to load dataset detail.",
          );
        }
      }
    }

    void loadDatasetDetail();

    return () => {
      active = false;
    };
  }, [selectedDatasetId]);

  useEffect(() => {
    setRenameDraft(selectedDataset?.summary?.title ?? "");
  }, [selectedDataset?.id, selectedDataset?.summary?.title]);

  useEffect(() => {
    let active = true;

    async function loadRelevantSources() {
      try {
        const payload = await fetchJson<RelevantDatasetsResponse>(`/datasets/relevant/${selectedCategory}`);
        if (active) {
          setRelevantSources(dedupeRelevantSources(payload.items));
        }
      } catch (sourceError) {
        if (active) {
          setError(
            sourceError instanceof Error ? sourceError.message : "Failed to load relevant sources.",
          );
        }
      }
    }

    void loadRelevantSources();

    return () => {
      active = false;
    };
  }, [selectedCategory]);

  useEffect(() => {
    if (terminalViewMode === "ingest") {
      setIsSourceInspectorOpen(false);
      setIsEditingInspectorName(false);
      setIsChatWorkspaceOpen(false);
    }
  }, [terminalViewMode]);

  useEffect(() => {
    setIsSourceInspectorOpen(false);
    setIsEditingInspectorName(false);
  }, [selectedCategory]);

  const openChatWorkspace = useCallback(() => {
    setTerminalViewMode("intelligence");
    setIsEditingInspectorName(false);
    setIsSourceInspectorOpen(false);
    setIsChatWorkspaceOpen(true);
  }, []);

  const closeChatWorkspace = useCallback(() => {
    setIsChatWorkspaceOpen(false);
  }, []);

  const terminalText = useMemo(
    () =>
      buildTerminalText({
        scores,
        specialists,
        selectedCategory,
        selectedDataset,
      }),
    [scores, selectedCategory, selectedDataset, specialists],
  );

  const selectedSpecialist = specialists?.scores[selectedCategory] ?? null;
  const sourceInspectorDataset =
    isSourceInspectorOpen && selectedDataset?.id === selectedDatasetId ? selectedDataset : null;
  const sourceInspectorMetrics = sourceInspectorDataset?.summary?.key_metrics ?? {};
  const sourceInspectorScores = sourceInspectorDataset
    ? Object.entries(sourceInspectorDataset.scores).sort(
        (left, right) => right[1].final_score - left[1].final_score,
      )
    : [];
  const recentChatEntries = chatHistory.slice(-6);

  useEffect(() => {
    const nextScore = scores?.scores[selectedCategory];
    setForecastTargetY(getDefaultForecastTarget(nextScore));
    setForecastTargetDate(getDefaultForecastDate());
    setForecastData(null);
    setForecastError(null);
  }, [scores?.scores, selectedCategory]);

  const loadForecast = useCallback(
    async (options?: { category?: string; announce?: boolean }) => {
      const category = options?.category ?? selectedCategory;
      const parsedTargetY = Number(forecastTargetY);

      if (!Number.isFinite(parsedTargetY)) {
        setForecastError("Enter a numeric target score before generating the forecast.");
        return;
      }

      if (forecastMode === "required_rate" && !forecastTargetDate) {
        setForecastError("Choose a target date for required-rate mode.");
        return;
      }

      setForecastError(null);
      setIsForecastLoading(true);

      if (options?.announce ?? true) {
        appendProcessEntry(
          `building ${category} forecast | mode=${forecastMode} | target=${parsedTargetY.toFixed(1)}`,
          "info",
        );
      }

      try {
        const query = new URLSearchParams({
          mode: forecastMode,
          target_y: parsedTargetY.toString(),
          forecast_periods: forecastPeriods.toString(),
        });

        if (forecastMode === "required_rate") {
          query.set("target_date", forecastTargetDate);
        }

        const payload = await fetchJson<CategoryForecastResponse>(
          `/scores/forecast/${category}?${query.toString()}`,
        );
        setForecastData(payload);
        appendProcessEntry(`forecast ready -> ${category} (${payload.mode})`, "success");
      } catch (forecastLoadError) {
        const message =
          forecastLoadError instanceof Error
            ? forecastLoadError.message
            : "Failed to generate forecast.";
        setForecastError(message);
        appendProcessEntry(`forecast failure -> ${category} | ${message}`, "warn");
      } finally {
        setIsForecastLoading(false);
      }
    },
    [
      appendProcessEntry,
      forecastMode,
      forecastPeriods,
      forecastTargetDate,
      forecastTargetY,
      selectedCategory,
    ],
  );

  useEffect(() => {
    if (!showForecastPanel) {
      return;
    }

    void loadForecast({ announce: false });
  }, [loadForecast, selectedCategory, showForecastPanel]);

  function renderReasoningStep(step: AgentReasoningStep) {
    return (
      <section key={`${step.tool_name}-${step.step}`} className="chat-trace-step">
        <div className="chat-trace-step-top">
          <span>Step {step.step}</span>
          <strong>{step.title}</strong>
        </div>
        <p className="chat-trace-summary">{step.summary}</p>

        {Object.keys(step.args ?? {}).length ? (
          <div className="chat-trace-args">
            {Object.entries(step.args).map(([key, value]) => (
              <span key={key}>
                {key}={typeof value === "string" ? value : JSON.stringify(value)}
              </span>
            ))}
          </div>
        ) : null}

        {step.scoring_explanation ? (
          <div className="chat-score-trace">
            <div className="chat-score-trace-overview">
              <div>
                <span>Category</span>
                <strong>{formatCategoryLabel(step.scoring_explanation.category)}</strong>
              </div>
              <div>
                <span>Aggregate</span>
                <strong>{formatDecimal(step.scoring_explanation.aggregated_score)}</strong>
              </div>
              <div>
                <span>Datasets</span>
                <strong>{step.scoring_explanation.dataset_count}</strong>
              </div>
              <div>
                <span>Weight</span>
                <strong>{formatDecimal(step.scoring_explanation.importance_weight, 2)}</strong>
              </div>
            </div>

            <div className="chat-score-trace-formulas">
              <span>{step.scoring_explanation.scoring_formula}</span>
              <span>{step.scoring_explanation.aggregation_formula}</span>
              <span>{step.scoring_explanation.benchmark_formula}</span>
              {!step.scoring_explanation.importance_weight_used_in_final_score ? (
                <span>
                  Importance weight is stored for context and is not applied to the per-dataset final score.
                </span>
              ) : null}
            </div>

            <div className="chat-score-trace-contributors">
              {step.scoring_explanation.top_contributors.map((contributor) => (
                <article key={contributor.dataset_id} className="chat-score-contributor">
                  <div className="chat-score-contributor-top">
                    <strong>{contributor.title ?? truncateMiddle(contributor.source_ref, 44)}</strong>
                    <span>{formatTimestamp(contributor.created_at)}</span>
                  </div>
                  <p className="chat-score-contributor-source">{contributor.source_ref}</p>
                  <div className="chat-score-contributor-metrics">
                    <span>final {formatDecimal(contributor.final_score)}</span>
                    <span>sim {formatDecimal(contributor.similarity, 3)}</span>
                    <span>bench {formatDecimal(contributor.benchmark_eval, 3)}</span>
                    <span>share {formatDecimal(contributor.contribution_weight * 100)}%</span>
                  </div>
                  <p className="chat-score-contributor-equation">{contributor.score_equation}</p>
                  {contributor.benchmark_breakdown.components.length ? (
                    <div className="chat-score-component-list">
                      {contributor.benchmark_breakdown.components.map((component) => (
                        <div
                          key={`${contributor.dataset_id}-${component.metric}`}
                          className="chat-score-component"
                        >
                          <div className="chat-score-component-top">
                            <strong>{component.label}</strong>
                            <span>
                              raw {formatDecimal(component.raw_value, 2)} | normalized{" "}
                              {formatDecimal(component.normalized_score, 3)}
                            </span>
                          </div>
                          <p>{component.formula}</p>
                          <p>{component.interpretation}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="dataset-empty">
                      No benchmark metric breakdown available for this dataset.
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>
        ) : step.result_preview ? (
          <pre className="chat-trace-preview">{step.result_preview}</pre>
        ) : null}
      </section>
    );
  }

  function renderChatEntry(entry: ChatHistoryItem, index: number, mode: "workspace" | "preview") {
    const isWorkspace = mode === "workspace";
    const toolCount = entry.toolCalls?.length ?? 0;
    const reasoningCount = entry.reasoningTrace?.length ?? 0;

    return (
      <article
        key={`${mode}-${entry.role}-${index}`}
        className={`chat-bubble chat-bubble-${entry.role}${isWorkspace ? " chat-bubble-workspace" : " chat-bubble-preview"}`}
      >
        <div className="chat-role">{entry.role}</div>
        <p>{entry.content}</p>
        {!isWorkspace && (toolCount || reasoningCount) ? (
          <div className="chat-preview-meta">
            {reasoningCount ? <span>{reasoningCount} thinking steps</span> : null}
            {toolCount ? <span>{toolCount} tool calls</span> : null}
          </div>
        ) : null}
        {entry.attachments?.length ? (
          <div className="chat-attachments">
            {entry.attachments.map((attachment) => (
              <a
                key={attachment.artifact_id}
                className="chat-attachment"
                href={resolveApiUrl(attachment.download_url)}
                download={attachment.filename}
              >
                <div className="chat-attachment-top">
                  <strong>{attachment.label}</strong>
                  <span>Download Clip</span>
                </div>
                <div className="chat-attachment-meta">
                  <span>{attachment.filename}</span>
                  {attachment.size_bytes ? <span>{formatFileSize(attachment.size_bytes)}</span> : null}
                  {attachment.created_at ? <span>{formatTimestamp(attachment.created_at)}</span> : null}
                </div>
                {attachment.source_ref ? <p>{attachment.source_ref}</p> : null}
              </a>
            ))}
          </div>
        ) : null}
        {isWorkspace && entry.toolCalls?.length ? (
          <div className="chat-tools">
            {entry.toolCalls.map((tool, toolIndex) => (
              <span key={`${tool.name}-${toolIndex}`}>
                {tool.name ?? "tool"}
                {tool.result ? " loaded" : ""}
              </span>
            ))}
          </div>
        ) : null}
        {isWorkspace && entry.reasoningTrace?.length ? (
          <div className="chat-trace">{entry.reasoningTrace.map(renderReasoningStep)}</div>
        ) : null}
      </article>
    );
  }

  function resetDatasourceForm(nextMode: DatasourceMode) {
    setDatasourceMode(nextMode);
    setDatasourceUrl("");
    setWebscrapeUrl("");
    setTranscriptText("");
    setScrapeTargets("");
    setDatasourceLabel("");
    setDatasourceFile(null);
  }

  async function pollIngestDataset(datasetId: string) {
    appendProcessEntry(`polling dataset lifecycle -> ${datasetId}`, "info");

    for (let attempt = 1; attempt <= 30; attempt += 1) {
      const dataset = await fetchJson<DatasetDetailResponse>(`/datasets/${datasetId}`);
      setIngestResult(dataset);
      setSelectedDatasetId(dataset.id);

      const summaryTitle = dataset.summary?.title ?? "--";
      const scoreCategories = Object.keys(dataset.scores ?? {});
      const consoleLines = [
        "DATASOURCE INGEST CONSOLE",
        "=========================",
        "",
        `DATASET ID     : ${dataset.id}`,
        `SOURCE         : ${dataset.source_ref}`,
        `INPUT TYPE     : ${dataset.input_type}`,
        `STATUS         : ${dataset.status}`,
        `TITLE          : ${summaryTitle}`,
        `GEOGRAPHY      : ${dataset.summary?.geography ?? "--"}`,
        `TIME PERIOD    : ${dataset.summary?.time_period ?? "--"}`,
        "",
        "KEY METRICS",
        "-----------",
        ...(Object.entries(dataset.summary?.key_metrics ?? {}).length
          ? Object.entries(dataset.summary?.key_metrics ?? {}).map(
              ([key, value]) => `${key} = ${value ?? "null"}`,
            )
          : ["No key metrics extracted yet."]),
        "",
        "SCORE RESULTS",
        "-------------",
        ...(scoreCategories.length
          ? scoreCategories.map((category) => {
              const detail = dataset.scores[category];
              return `${category} final=${detail.final_score.toFixed(2)} sim=${detail.similarity.toFixed(3)} bench=${detail.benchmark_eval.toFixed(3)}`;
            })
          : ["Scores not available yet."]),
      ];

      setIngestConsole(consoleLines.join("\n"));

      if (attempt === 1) {
        appendProcessEntry(`dataset record created -> ${datasetId}`, "info");
      }

      appendProcessEntry(`attempt ${attempt} | dataset status=${dataset.status}`, "info");

      if (dataset.status === "complete") {
        appendProcessEntry(`ingest complete -> ${summaryTitle}`, "success");
        appendProcessEntry(`stored summary and scores for ${dataset.id}`, "success");
        await loadDashboardData();
        return;
      }

      if (dataset.status === "error") {
        const message = dataset.error_msg ?? "Unknown ingest failure.";
        appendProcessEntry(`ingest failed -> ${message}`, "warn");
        setError(message);
        return;
      }

      if (attempt === 2) {
        appendProcessEntry("pipeline step observed -> classifier / summariser / embedder / scorer", "info");
      }

      await sleep(1500);
    }

    appendProcessEntry(`ingest polling timed out for ${datasetId}`, "warn");
  }

  async function submitDatasource() {
    if (isSubmittingDatasource) {
      return;
    }

    const isEndpointMode = datasourceMode === "endpoint";
    const isWebscrapeMode = datasourceMode === "webscrape";
    const isTranscriptMode = datasourceMode === "transcript";
    const endpointUrl = datasourceUrl.trim();
    const nextWebscrapeUrl = webscrapeUrl.trim();
    const nextTranscriptText = transcriptText.trim();

    if (isEndpointMode && !endpointUrl) {
      setError("Paste an endpoint URL before submitting.");
      return;
    }

    if (isWebscrapeMode && !nextWebscrapeUrl) {
      setError("Paste a web page URL before submitting.");
      return;
    }

    if (isTranscriptMode && !nextTranscriptText) {
      setError("Paste an interview transcript before submitting.");
      return;
    }

    if (datasourceMode === "file" && !datasourceFile) {
      setError("Attach a CSV file before submitting.");
      return;
    }

    setError(null);
    setIsSubmittingDatasource(true);
    setTerminalViewMode("ingest");
    setShowProcessPanel(true);
    setIngestResult(null);
    setIngestDatasetId(null);
    setIngestConsole(
      [
        "DATASOURCE INGEST CONSOLE",
        "=========================",
        "",
        `MODE           : ${isEndpointMode ? "endpoint" : isWebscrapeMode ? "webscrape" : isTranscriptMode ? "interview transcript" : "csv upload"}`,
        `LABEL          : ${datasourceLabel || "--"}`,
        `SOURCE         : ${
          isEndpointMode
            ? endpointUrl
            : isWebscrapeMode
              ? nextWebscrapeUrl
              : isTranscriptMode
                ? datasourceLabel.trim() || "inline interview transcript"
                : datasourceFile?.name ?? "--"
        }`,
        `SCRAPE TARGETS : ${isWebscrapeMode ? scrapeTargets || "auto-derived" : "--"}`,
        `TRANSCRIPT LEN : ${isTranscriptMode ? `${nextTranscriptText.length} chars` : "--"}`,
        "",
        "Preparing request payload...",
      ].join("\n"),
    );
    appendProcessEntry(
      `datasource submission started -> ${
        isEndpointMode
          ? endpointUrl
          : isWebscrapeMode
            ? nextWebscrapeUrl
            : isTranscriptMode
              ? datasourceLabel.trim() || "interview transcript"
              : datasourceFile?.name ?? "file"
      }`,
      "info",
    );

    try {
      const formData = new FormData();
      if (datasourceLabel.trim()) {
        formData.set("label", datasourceLabel.trim());
      }

      if (isEndpointMode) {
        formData.set("endpoint_url", endpointUrl);
        appendProcessEntry("dispatch ingest endpoint request", "info");
      } else if (isWebscrapeMode) {
        formData.set("webscrape_url", nextWebscrapeUrl);
        if (scrapeTargets.trim()) {
          formData.set("scrape_targets", scrapeTargets.trim());
        }
        appendProcessEntry("dispatch webscrape request and await extracted payload", "info");
      } else if (isTranscriptMode) {
        formData.set("transcript_text", nextTranscriptText);
        appendProcessEntry("dispatch interview transcript request", "info");
      } else if (datasourceFile) {
        formData.set("file", datasourceFile, datasourceFile.name);
        appendProcessEntry("dispatch csv upload request", "info");
      }

      const response = await fetch(`${API_BASE_URL}/ingest`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const payload = (await response.json()) as IngestResponse;
      setIngestDatasetId(payload.dataset_id);
      appendProcessEntry(`dataset queued -> ${payload.dataset_id}`, "success");
      appendProcessEntry("waiting for pipeline status changes in backend", "info");

      setIngestConsole((current) =>
        `${current}\nQueued dataset: ${payload.dataset_id}\nBackend message: ${payload.message}`,
      );

      await pollIngestDataset(payload.dataset_id);
      resetDatasourceForm(datasourceMode);
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Datasource submission failed.";
      setError(message);
      appendProcessEntry(`datasource ingest failed | ${message}`, "warn");
      setIngestConsole((current) => `${current}\n\nERROR\n-----\n${message}`);
    } finally {
      setIsSubmittingDatasource(false);
    }
  }

  async function runSingleSpecialist(category: string) {
    setRunningCategory(category);
    appendProcessEntry(`dispatch specialist agent -> ${category}`, "info");

    try {
      appendProcessEntry(`loading benchmark context and evidence for ${category}`, "info");
      const payload = await fetchJson<RunSpecialistResponse>(`/specialist-scores/run/${category}`, {
        method: "POST",
      });
      appendProcessEntry(
        `${category} completed | score=${payload.result.score} | band=${payload.result.status_label}`,
        "success",
      );
      appendProcessEntry(`refreshing dashboard after ${category} run`, "info");
      await loadDashboardData();
      setSelectedCategory(category);
    } catch (runError) {
      const message = runError instanceof Error ? runError.message : `Failed to run ${category}.`;
      setError(message);
      appendProcessEntry(`agent failure -> ${category} | ${message}`, "warn");
    } finally {
      setRunningCategory(null);
    }
  }

  async function runAllSpecialists() {
    setRunningAllAgents(true);
    appendProcessEntry("dispatch all specialist agents", "info");

    try {
      appendProcessEntry("dispatching housing, employment, transportation, healthcare, placemaking to parallel workers", "info");
      const payload = await fetchJson<RunAllSpecialistsResponse>("/specialist-scores/run-all", {
        method: "POST",
      });
      payload.results.forEach((result) => {
        appendProcessEntry(
          `${result.category} persisted | score=${result.score} | band=${result.status_label}`,
          "success",
        );
      });
      appendProcessEntry("refreshing dashboard after full specialist sweep", "info");
      await loadDashboardData();
      const latestResult = payload.results[payload.results.length - 1];
      if (latestResult?.category) {
        setSelectedCategory(latestResult.category);
      }
    } catch (runError) {
      const message = runError instanceof Error ? runError.message : "Failed to run all agents.";
      setError(message);
      appendProcessEntry(`global agent sweep failed | ${message}`, "warn");
    } finally {
      setRunningAllAgents(false);
    }
  }

  async function sendChatMessage() {
    const message = chatDraft.trim();
    if (!message || isChatting) {
      return;
    }

    openChatWorkspace();
    const nextHistory = [...chatHistory, { role: "user" as const, content: message }];
    setChatHistory(nextHistory);
    setChatDraft("");
    setIsChatting(true);
    appendProcessEntry(`planner chat query -> ${message}`, "info");

    try {
      const payload = await fetchJson<AgentChatResponse>("/agent/chat", {
        method: "POST",
        body: JSON.stringify({
          message,
          history: nextHistory
            .slice(0, -1)
            .map((item) => ({ role: item.role, content: item.content })),
        }),
      });

      setChatHistory((current) => [
        ...current,
        {
          role: "assistant",
          content: payload.response,
          toolCalls: payload.tool_calls,
          reasoningTrace: payload.reasoning_trace,
          attachments: payload.attachments,
        },
      ]);
      appendProcessEntry(
        `planner chat response received | steps=${payload.reasoning_trace.length} | tools=${payload.tool_calls.map((tool) => tool.name).join(", ") || "none"}`,
        "success",
      );
      payload.reasoning_trace.forEach((step) => {
        appendProcessEntry(`chat step ${step.step} -> ${step.title}`, "info");
      });
    } catch (chatError) {
      const messageText = chatError instanceof Error ? chatError.message : "Chat request failed.";
      setError(messageText);
      appendProcessEntry(`planner chat failure | ${messageText}`, "warn");
    } finally {
      setIsChatting(false);
    }
  }

  async function renameSelectedDataset() {
    if (!selectedDatasetId || !renameDraft.trim() || isRenamingDataset) {
      return;
    }

    setIsRenamingDataset(true);
    setError(null);

    try {
      const payload = await fetchJson<DatasetDetailResponse>(`/datasets/${selectedDatasetId}`, {
        method: "PATCH",
        body: JSON.stringify({ summary_title: renameDraft.trim() }),
      });

      setSelectedDataset(payload);
      setRenameDraft(payload.summary?.title ?? "");
      setIsEditingInspectorName(false);
      setRelevantSources((current) =>
        current.map((item) =>
          item.id === payload.id
            ? { ...item, title: payload.summary?.title ?? item.title }
            : item,
        ),
      );
      appendProcessEntry(`summary title updated -> ${payload.summary?.title ?? "--"}`, "success");
    } catch (renameError) {
      const message =
        renameError instanceof Error ? renameError.message : "Failed to rename dataset.";
      setError(message);
      appendProcessEntry(`rename failed | ${message}`, "warn");
    } finally {
      setIsRenamingDataset(false);
    }
  }

  return (
    <main className="terminal-shell">
      <div className="terminal-background" aria-hidden="true">
        <Dither
          colorNum={4}
          disableAnimation={false}
          enableMouseInteraction={false}
          mouseRadius={1.15}
          pixelSize={3}
          waveAmplitude={0.36}
          waveColor={[0.4, 0.17, 0.06]}
          waveFrequency={2.05}
          waveSpeed={0.04}
        />
      </div>
      <div className="scanlines" />
      <section className="terminal-frame">
        <header className="hero-bar">
          <div>
            <p className="eyebrow">Forecast</p>
            <h1>WATERLOO REGION 1 MILLION DASHBOARD</h1>
          </div>
          <div className="hero-meta">
            <span>{isLoading ? "BOOTING" : "LIVE"}</span>
            <span>{isRefreshing ? "SYNCING" : "IDLE"}</span>
            <span>{formatTimestamp(specialists?.last_updated ?? scores?.last_updated)}</span>
          </div>
        </header>

        <section className="ticker">
          <span>DATASETS {scores?.dataset_count ?? "--"}</span>
          <span>API {API_BASE_URL}</span>
          <span>SPECIALIST RUNS {Object.values(specialists?.scores ?? {}).filter(Boolean).length}</span>
          <span>DISPLAY MODE TERMINAL</span>
        </section>

        <section className="control-bar">
          <button
            className={`terminal-button${terminalViewMode === "ingest" ? " terminal-button-primary" : ""}`}
            onClick={() => setTerminalViewMode((current) => (current === "ingest" ? "intelligence" : "ingest"))}
            type="button"
          >
            {terminalViewMode === "ingest" ? "RETURN TO INTELLIGENCE" : "ADD DATASOURCE"}
          </button>
          <button
            className="terminal-button"
            onClick={() => {
              setIsRefreshing(true);
              void loadDashboardData();
            }}
            type="button"
          >
            REFRESH GRID
          </button>
          <button
            className="terminal-button terminal-button-primary"
            disabled={runningAllAgents}
            onClick={() => void runAllSpecialists()}
            type="button"
          >
            {runningAllAgents ? "RUNNING ALL AGENTS" : "RUN ALL SUBAGENTS"}
          </button>
          <button
            className="terminal-button"
            disabled={runningCategory === selectedCategory}
            onClick={() => void runSingleSpecialist(selectedCategory)}
            type="button"
          >
            {runningCategory === selectedCategory
              ? `RUNNING ${selectedCategory.toUpperCase()}`
              : `RUN ${selectedCategory.toUpperCase()} AGENT`}
          </button>
          <button
            className="terminal-button"
            onClick={() => setShowProcessPanel((current) => !current)}
            type="button"
          >
            {showProcessPanel ? "HIDE PROCESS WINDOW" : "SHOW PROCESS WINDOW"}
          </button>
          <button
            className={`terminal-button${showForecastPanel ? " terminal-button-primary" : ""}`}
            type="button"
            onClick={() => {
              setShowForecastPanel((current) => !current);
            }}
          >
            {showForecastPanel
              ? `HIDE ${selectedCategory.toUpperCase()} FORECAST`
              : `SHOW ${selectedCategory.toUpperCase()} FORECAST`}
          </button>
        </section>

        <section className="score-grid">
          {CATEGORY_ORDER.map((category) => {
            const aggregate = scores?.scores[category];
            const specialist = specialists?.scores[category];
            const isActive = selectedCategory === category;

            return (
              <div
                key={category}
                className={`score-card${isActive ? " score-card-active" : ""}`}
              >
                <button
                  className="score-card-main"
                  onClick={() => setSelectedCategory(category)}
                  type="button"
                >
                  <span className="score-card-label">{category}</span>
                  <strong>{aggregate?.toFixed(2) ?? "--"}</strong>
                  <span className="score-card-meta">
                    agent {specialist?.score ?? "--"} / band {specialist?.status_label ?? "NO RUN"}
                  </span>
                </button>
                <button
                  className="score-card-trigger"
                  disabled={runningCategory === category || runningAllAgents}
                  onClick={() => void runSingleSpecialist(category)}
                  type="button"
                >
                  {runningCategory === category ? "RUNNING" : "RUN AGENT"}
                </button>
              </div>
            );
          })}
        </section>

        <section
          className={`terminal-matrix${showProcessPanel ? " terminal-matrix-process-open" : ""}${
            showForecastPanel ? " terminal-matrix-forecast-open" : ""
          }`}
        >
          <div className={`panel registry-panel${showForecastPanel ? " registry-panel-hidden" : ""}`}>
            <div className="panel-header">
              <span>DATA REGISTRY</span>
              <span className="panel-subtle">LIVE DATA SOURCES</span>
            </div>

            <div className="dataset-table">
              <div className="dataset-table-head">
                <span>source</span>
                <span>type</span>
                <span>status</span>
                <span>created</span>
              </div>

              {datasets?.items.map((item) => (
                <button
                  key={item.id}
                  className={`dataset-row${selectedDatasetId === item.id ? " dataset-row-active" : ""}`}
                  onClick={() => {
                    setIsEditingInspectorName(false);
                    setIsSourceInspectorOpen(false);
                    setIsChatWorkspaceOpen(false);
                    setSelectedDatasetId(item.id);
                  }}
                  type="button"
                >
                  <span title={item.source_ref}>{item.source_ref}</span>
                  <span>{item.input_type}</span>
                  <span>{item.status}</span>
                  <span>{formatTimestamp(item.created_at)}</span>
                </button>
              ))}

              {!datasets?.items.length && <div className="dataset-empty">No datasets available.</div>}
            </div>
          </div>

          <div className={`panel terminal-panel${showForecastPanel ? " terminal-panel-forecast-open" : ""}`}>
            <div className="panel-header">
              <span>
                {terminalViewMode === "ingest"
                  ? "DATASOURCE CONSOLE"
                  : isChatWorkspaceOpen
                    ? "PLANNER CHAT"
                  : isSourceInspectorOpen
                    ? "DATASET DETAIL"
                    : showForecastPanel
                      ? "FORECAST CONSOLE"
                    : "INTELLIGENCE TEXTBOX"}
              </span>
              <span className="panel-subtle">
                {terminalViewMode === "ingest"
                  ? "INGEST + SORTING FLOW"
                  : isChatWorkspaceOpen
                    ? isChatting
                      ? "MODEL THINKING + TOOL CALLS"
                      : "CHAT WORKSPACE"
                  : isSourceInspectorOpen
                    ? sourceInspectorDataset?.summary?.title ??
                      sourceInspectorDataset?.source_ref ??
                      "LOADING DATASET"
                    : showForecastPanel
                      ? `${selectedCategory.toUpperCase()} FORECAST`
                    : `${selectedCategory.toUpperCase()} FOCUS`}
              </span>
            </div>

            {terminalViewMode === "ingest" ? (
              <div className="datasource-console">
                <div className="datasource-tabs">
                  <button
                    className={`datasource-tab${datasourceMode === "endpoint" ? " datasource-tab-active" : ""}`}
                    onClick={() => resetDatasourceForm("endpoint")}
                    type="button"
                  >
                    API ENDPOINT
                  </button>
                  <button
                    className={`datasource-tab${datasourceMode === "file" ? " datasource-tab-active" : ""}`}
                    onClick={() => resetDatasourceForm("file")}
                    type="button"
                  >
                    CSV FILE
                  </button>
                  <button
                    className={`datasource-tab${datasourceMode === "webscrape" ? " datasource-tab-active" : ""}`}
                    onClick={() => resetDatasourceForm("webscrape")}
                    type="button"
                  >
                    WEBSCRAPE
                  </button>
                  <button
                    className={`datasource-tab${datasourceMode === "transcript" ? " datasource-tab-active" : ""}`}
                    onClick={() => resetDatasourceForm("transcript")}
                    type="button"
                  >
                    INTERVIEW
                  </button>
                </div>

                <div className="datasource-form">
                  <label className="datasource-field">
                    <span>LABEL</span>
                    <input
                      onChange={(event) => setDatasourceLabel(event.target.value)}
                      placeholder="Optional display label"
                      value={datasourceLabel}
                    />
                  </label>

                  {datasourceMode === "endpoint" ? (
                    <label className="datasource-field datasource-field-grow">
                      <span>API URL</span>
                      <textarea
                        onChange={(event) => setDatasourceUrl(event.target.value)}
                        placeholder="https://example.com/api/..."
                        rows={5}
                        value={datasourceUrl}
                      />
                    </label>
                  ) : datasourceMode === "webscrape" ? (
                    <>
                      <label className="datasource-field datasource-field-grow">
                        <span>WEB PAGE URL</span>
                        <textarea
                          onChange={(event) => setWebscrapeUrl(event.target.value)}
                          placeholder="https://example.com/page-to-scrape"
                          rows={4}
                          value={webscrapeUrl}
                        />
                      </label>

                      <label className="datasource-field">
                        <span>SCRAPE TARGETS</span>
                        <input
                          onChange={(event) => setScrapeTargets(event.target.value)}
                          placeholder="Optional comma-separated targets, e.g. WRHN Midtown, current wait time"
                          value={scrapeTargets}
                        />
                      </label>
                    </>
                  ) : datasourceMode === "transcript" ? (
                    <label className="datasource-field datasource-field-grow">
                      <span>INTERVIEW TRANSCRIPT</span>
                      <textarea
                        onChange={(event) => setTranscriptText(event.target.value)}
                        placeholder="Paste the interview transcript here, including speaker turns if available."
                        rows={8}
                        value={transcriptText}
                      />
                    </label>
                  ) : (
                    <label className="datasource-field datasource-field-grow">
                      <span>CSV ATTACHMENT</span>
                      <input
                        accept=".csv,text/csv"
                        onChange={(event) => {
                          const nextFile = event.target.files?.[0] ?? null;
                          setDatasourceFile(nextFile);
                        }}
                        type="file"
                      />
                    </label>
                  )}

                  <div className="datasource-actions">
                    <button
                      className="terminal-button terminal-button-primary"
                      disabled={isSubmittingDatasource}
                      onClick={() => void submitDatasource()}
                      type="button"
                    >
                      {isSubmittingDatasource ? "INGESTING" : "RUN SORTING PROCESS"}
                    </button>
                    {ingestDatasetId ? (
                      <span className="datasource-status">DATASET {truncateMiddle(ingestDatasetId, 26)}</span>
                    ) : null}
                  </div>
                </div>

                <textarea
                  className="terminal-textbox"
                  readOnly
                  spellCheck={false}
                  value={error ? `${ingestConsole}\n\nERROR\n-----\n${error}` : ingestConsole}
                />
              </div>
            ) : isChatWorkspaceOpen ? (
              <div className="chat-workspace">
                <div className="chat-workspace-top">
                  <div className="chat-workspace-heading">
                    <span>Central agent workspace</span>
                    <strong>
                      {chatHistory.length
                        ? "Live conversation with visible reasoning and tool activity"
                        : "Start a conversation to inspect model reasoning"}
                    </strong>
                  </div>
                  <button
                    aria-label="Close chat workspace"
                    className="dataset-inspector-close"
                    onClick={closeChatWorkspace}
                    type="button"
                  >
                    X
                  </button>
                </div>

                <div className="chat-thread chat-thread-workspace">
                  {chatHistory.length ? (
                    chatHistory.map((entry, index) => renderChatEntry(entry, index, "workspace"))
                  ) : (
                    <div className="dataset-empty">
                      Ask the planning agent about weak categories, evidence, or recommended interventions.
                    </div>
                  )}

                  {isChatting ? (
                    <article className="chat-bubble chat-bubble-assistant chat-bubble-workspace">
                      <div className="chat-role">assistant</div>
                      <p>Thinking through your request and preparing any tool calls needed to answer it.</p>
                      <div className="chat-thinking">
                        <span>Reasoning in progress</span>
                        <span>Tool activity will appear here when the response returns</span>
                      </div>
                    </article>
                  ) : null}
                </div>

                <div className="chat-input-bar chat-input-bar-workspace">
                  <textarea
                    className="chat-input"
                    onChange={(event) => setChatDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void sendChatMessage();
                      }
                    }}
                    placeholder="Ask the central planning agent..."
                    rows={4}
                    value={chatDraft}
                  />
                  <button
                    className="terminal-button terminal-button-primary"
                    disabled={!chatDraft.trim() || isChatting}
                    onClick={() => void sendChatMessage()}
                    type="button"
                  >
                    {isChatting ? "THINKING" : "SEND"}
                  </button>
                </div>
              </div>
            ) : isSourceInspectorOpen ? (
              <div className="dataset-inspector">
                <div className="dataset-inspector-top">
                  <div className="dataset-inspector-heading">
                    <span>Expanded dataset view</span>
                    {isEditingInspectorName ? (
                      <div className="dataset-inspector-rename">
                        <input
                          onChange={(event) => setRenameDraft(event.target.value)}
                          placeholder="Summary title"
                          value={renameDraft}
                        />
                        <div className="dataset-inspector-rename-actions">
                          <button
                            className="terminal-button terminal-button-primary"
                            disabled={!renameDraft.trim() || isRenamingDataset}
                            onClick={() => void renameSelectedDataset()}
                            type="button"
                          >
                            {isRenamingDataset ? "Saving" : "Save"}
                          </button>
                          <button
                            className="terminal-button"
                            onClick={() => {
                              setRenameDraft(sourceInspectorDataset?.summary?.title ?? "");
                              setIsEditingInspectorName(false);
                            }}
                            type="button"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="dataset-inspector-title-row">
                        <strong>
                          {sourceInspectorDataset?.summary?.title ??
                            sourceInspectorDataset?.source_ref ??
                            "Loading dataset..."}
                        </strong>
                        <button
                          aria-label="Rename dataset"
                          className="dataset-inspector-edit"
                          onClick={() => setIsEditingInspectorName(true)}
                          type="button"
                        >
                          ✎
                        </button>
                      </div>
                    )}
                  </div>
                  <button
                    aria-label="Minimize dataset detail"
                    className="dataset-inspector-close"
                    onClick={() => {
                      setIsEditingInspectorName(false);
                      setIsSourceInspectorOpen(false);
                    }}
                    type="button"
                  >
                    X
                  </button>
                </div>

                {sourceInspectorDataset ? (
                  <div className="dataset-inspector-body">
                    <section className="dataset-inspector-section">
                      <div className="dataset-inspector-meta">
                        <div>
                          <span>ID</span>
                          <strong>{sourceInspectorDataset.id}</strong>
                        </div>
                        <div>
                          <span>Source</span>
                          <strong>{sourceInspectorDataset.source_ref}</strong>
                        </div>
                        <div>
                          <span>Input type</span>
                          <strong>{sourceInspectorDataset.input_type}</strong>
                        </div>
                        <div>
                          <span>Status</span>
                          <strong>{sourceInspectorDataset.status}</strong>
                        </div>
                        <div>
                          <span>Geography</span>
                          <strong>{sourceInspectorDataset.summary?.geography ?? "--"}</strong>
                        </div>
                        <div>
                          <span>Time period</span>
                          <strong>{sourceInspectorDataset.summary?.time_period ?? "--"}</strong>
                        </div>
                      </div>
                    </section>

                    <section className="dataset-inspector-section">
                      <span className="dataset-inspector-label">Civic relevance</span>
                      <p>
                        {sourceInspectorDataset.summary?.civic_relevance ??
                          "No civic relevance summary available for this dataset."}
                      </p>
                    </section>

                    <section className="dataset-inspector-section">
                      <span className="dataset-inspector-label">Data quality notes</span>
                      <p>
                        {sourceInspectorDataset.summary?.data_quality_notes ??
                          "No data quality notes were generated for this dataset."}
                      </p>
                    </section>

                    <section className="dataset-inspector-section">
                      <span className="dataset-inspector-label">Key metrics</span>
                      {Object.entries(sourceInspectorMetrics).length ? (
                        <div className="dataset-inspector-grid">
                          {Object.entries(sourceInspectorMetrics).map(([metric, value]) => (
                            <div key={metric} className="dataset-inspector-stat">
                              <span>{formatCategoryLabel(metric)}</span>
                              <strong>{value ?? "null"}</strong>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="dataset-empty">No key metrics available.</div>
                      )}
                    </section>

                    <section className="dataset-inspector-section">
                      <span className="dataset-inspector-label">Scores</span>
                      {sourceInspectorScores.length ? (
                        <div className="dataset-inspector-grid">
                          {sourceInspectorScores.map(([category, detail]) => (
                            <div key={category} className="dataset-inspector-stat">
                              <span>{formatCategoryLabel(category)}</span>
                              <strong>{detail.final_score.toFixed(2)}</strong>
                              <small>
                                sim {detail.similarity.toFixed(3)} | bench {detail.benchmark_eval.toFixed(3)}
                              </small>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="dataset-empty">No scores available.</div>
                      )}
                    </section>

                    {sourceInspectorDataset.error_msg ? (
                      <section className="dataset-inspector-section">
                        <span className="dataset-inspector-label">Error</span>
                        <p>{sourceInspectorDataset.error_msg}</p>
                      </section>
                    ) : null}
                  </div>
                ) : (
                  <div className="dataset-empty">Loading selected dataset...</div>
                )}
              </div>
            ) : showForecastPanel ? (
              <ForecastPanel
                categoryLabel={formatCategoryLabel(selectedCategory)}
                data={forecastData}
                error={forecastError}
                forecastPeriods={forecastPeriods}
                isLoading={isForecastLoading}
                mode={forecastMode}
                onClose={() => setShowForecastPanel(false)}
                onForecastPeriodsChange={setForecastPeriods}
                onGenerate={() => void loadForecast({ announce: true })}
                onModeChange={setForecastMode}
                onTargetDateChange={setForecastTargetDate}
                onTargetYChange={setForecastTargetY}
                targetDate={forecastTargetDate}
                targetY={forecastTargetY}
              />
            ) : (
              <textarea
                className="terminal-textbox"
                readOnly
                spellCheck={false}
                value={error ? `${terminalText}\n\nERROR\n-----\n${error}` : terminalText}
              />
            )}
          </div>

          <div className="panel sources-panel">
            <div className="panel-header">
              <span>RELEVANT SOURCES</span>
              <span className="panel-subtle">{selectedCategory.toUpperCase()} RELEVANCE</span>
            </div>

            <div className="sources-stack">
              <div className="sources-list">
                {relevantSources.length ? (
                  relevantSources.map((source) => (
                    <button
                      key={source.id}
                      className="source-card"
                      onClick={() => {
                        setIsEditingInspectorName(false);
                        setIsChatWorkspaceOpen(false);
                        setSelectedDatasetId(source.id);
                        setIsSourceInspectorOpen(true);
                      }}
                      type="button"
                    >
                      <div className="source-card-top">
                        <strong>{source.title ?? truncateMiddle(source.source_ref, 52)}</strong>
                        <span>{source.input_type}</span>
                      </div>
                      <p>
                        score {source.final_score.toFixed(2)} | sim {source.similarity.toFixed(3)} | bench{" "}
                        {source.benchmark_eval.toFixed(3)}
                      </p>
                      <div className="source-card-meta">
                        <span>{source.geography ?? "--"}</span>
                        <span>{source.time_period ?? "--"}</span>
                        <span>{formatTimestamp(source.created_at)}</span>
                      </div>
                    </button>
                  ))
                ) : (
                  <div className="dataset-empty">No relevant datasets found for the selected category.</div>
                )}
              </div>
            </div>
          </div>

          <div className="panel chat-panel">
            <div className="panel-header">
              <span>CHAT LAUNCHER</span>
              <span className="panel-subtle">
                {isChatWorkspaceOpen ? "WORKSPACE OPEN" : "OPEN IN INTELLIGENCE PANE"}
              </span>
            </div>

            <div className="chat-launcher">
              <div className="chat-launcher-status">
                <span>{chatHistory.length ? `${chatHistory.length} messages` : "No active chat yet"}</span>
                <span>{isChatting ? "Model thinking" : isChatWorkspaceOpen ? "Workspace active" : "Workspace closed"}</span>
              </div>

              <button
                className="terminal-button terminal-button-primary"
                onClick={openChatWorkspace}
                type="button"
              >
                {chatHistory.length ? "OPEN CHAT WORKSPACE" : "START CHAT IN MAIN PANE"}
              </button>

              <div className="chat-thread chat-thread-preview">
                {recentChatEntries.length ? (
                  recentChatEntries.map((entry, index) => (
                    <button
                      key={`preview-${entry.role}-${index}`}
                      className="chat-preview-trigger"
                      onClick={openChatWorkspace}
                      type="button"
                    >
                      {renderChatEntry(entry, index, "preview")}
                    </button>
                  ))
                ) : (
                  <div className="dataset-empty">
                    Open the chat workspace to talk with the central agent and inspect its reasoning.
                  </div>
                )}
              </div>
            </div>
          </div>

          {showProcessPanel ? (
            <div className="panel process-panel">
              <div className="panel-header">
                <span>PROCESS WINDOW</span>
                <span className="panel-subtle">
                  {runningAllAgents
                    ? "GLOBAL SWEEP ACTIVE"
                    : runningCategory
                      ? `${runningCategory.toUpperCase()} ACTIVE`
                      : "IDLE"}
                </span>
              </div>

              <div className="process-stream">
                {processEntries.length ? (
                  processEntries.map((entry) => (
                    <div key={entry.id} className={`process-line process-line-${entry.tone}`}>
                      <span>{formatTimestamp(entry.createdAt)}</span>
                      <span>{entry.message}</span>
                    </div>
                  ))
                ) : (
                  <div className="dataset-empty">No process output yet. Run a specialist agent to open the stream.</div>
                )}
              </div>
            </div>
          ) : null}
        </section>
      </section>
    </main>
  );
}
