"use client";

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
};

type AgentChatResponse = {
  response: string;
  tool_calls: { name?: string; result?: string }[];
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
type DatasourceMode = "endpoint" | "file" | "webscrape";

const CATEGORY_ORDER = [
  "housing",
  "employment",
  "transportation",
  "healthcare",
  "placemaking",
] as const;

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

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
      const specialistStatus = specialists?.scores[category]?.status_label ?? "NO RUN";
      return `${category.toUpperCase().padEnd(16)} agg=${String(
        aggregate?.toFixed?.(2) ?? "--",
      ).padStart(6)} | specialist=${String(specialistScore ?? "--").padStart(5)} | ${specialistStatus}`;
    }),
    "",
    `FOCUS CATEGORY : ${selectedCategory.toUpperCase()}`,
    `AGENT          : ${specialist?.agent_name ?? "--"}`,
    `STATUS         : ${specialist?.status_label ?? "--"}`,
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
  const [datasourceMode, setDatasourceMode] = useState<DatasourceMode>("endpoint");
  const [datasourceUrl, setDatasourceUrl] = useState("");
  const [webscrapeUrl, setWebscrapeUrl] = useState("");
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
      "Paste an API endpoint or attach a CSV file.",
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
    let active = true;

    async function loadRelevantSources() {
      try {
        const payload = await fetchJson<RelevantDatasetsResponse>(`/datasets/relevant/${selectedCategory}`);
        if (active) {
          setRelevantSources(payload.items);
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

  function resetDatasourceForm(nextMode: DatasourceMode) {
    setDatasourceMode(nextMode);
    setDatasourceUrl("");
    setWebscrapeUrl("");
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
    const endpointUrl = datasourceUrl.trim();
    const nextWebscrapeUrl = webscrapeUrl.trim();

    if (isEndpointMode && !endpointUrl) {
      setError("Paste an endpoint URL before submitting.");
      return;
    }

    if (isWebscrapeMode && !nextWebscrapeUrl) {
      setError("Paste a web page URL before submitting.");
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
        `MODE           : ${isEndpointMode ? "endpoint" : isWebscrapeMode ? "webscrape" : "csv upload"}`,
        `LABEL          : ${datasourceLabel || "--"}`,
        `SOURCE         : ${isEndpointMode ? endpointUrl : isWebscrapeMode ? nextWebscrapeUrl : datasourceFile?.name ?? "--"}`,
        `SCRAPE TARGETS : ${isWebscrapeMode ? scrapeTargets || "auto-derived" : "--"}`,
        "",
        "Preparing request payload...",
      ].join("\n"),
    );
    appendProcessEntry(
      `datasource submission started -> ${isEndpointMode ? endpointUrl : isWebscrapeMode ? nextWebscrapeUrl : datasourceFile?.name ?? "file"}`,
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
        `${category} completed | score=${payload.result.score} | status=${payload.result.status_label}`,
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
      appendProcessEntry("sequencing housing, employment, transportation, healthcare, placemaking", "info");
      const payload = await fetchJson<RunAllSpecialistsResponse>("/specialist-scores/run-all", {
        method: "POST",
      });
      payload.results.forEach((result) => {
        appendProcessEntry(
          `${result.category} persisted | score=${result.score} | status=${result.status_label}`,
          "success",
        );
      });
      appendProcessEntry("refreshing dashboard after full specialist sweep", "info");
      await loadDashboardData();
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
        },
      ]);
      appendProcessEntry(
        `planner chat response received | tools=${payload.tool_calls.map((tool) => tool.name).join(", ") || "none"}`,
        "success",
      );
    } catch (chatError) {
      const messageText = chatError instanceof Error ? chatError.message : "Chat request failed.";
      setError(messageText);
      appendProcessEntry(`planner chat failure | ${messageText}`, "warn");
    } finally {
      setIsChatting(false);
    }
  }

  return (
    <main className="terminal-shell">
      <div className="scanlines" />
      <section className="terminal-frame">
        <header className="hero-bar">
          <div>
            <p className="eyebrow">Forecast / Bloomberg-Style Terminal</p>
            <h1>MUNICIPAL INTELLIGENCE DASHBOARD</h1>
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
                    agent {specialist?.score ?? "--"} / {specialist?.status_label ?? "NO RUN"}
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

        <section className={`terminal-matrix${showProcessPanel ? " terminal-matrix-process-open" : ""}`}>
          <div className="panel registry-panel">
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
                  onClick={() => setSelectedDatasetId(item.id)}
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

          <div className="panel terminal-panel">
            <div className="panel-header">
              <span>{terminalViewMode === "ingest" ? "DATASOURCE CONSOLE" : "INTELLIGENCE TEXTBOX"}</span>
              <span className="panel-subtle">
                {terminalViewMode === "ingest" ? "INGEST + SORTING FLOW" : `${selectedCategory.toUpperCase()} FOCUS`}
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
                      onClick={() => setSelectedDatasetId(source.id)}
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
              <span>PLANNER CHATBOT</span>
              <span className="panel-subtle">CONNECTED TO AGENT TOOLS</span>
            </div>

            <div className="chat-thread">
              {chatHistory.length ? (
                chatHistory.map((entry, index) => (
                  <article
                    key={`${entry.role}-${index}`}
                    className={`chat-bubble chat-bubble-${entry.role}`}
                  >
                    <div className="chat-role">{entry.role}</div>
                    <p>{entry.content}</p>
                    {entry.toolCalls?.length ? (
                      <div className="chat-tools">
                        {entry.toolCalls.map((tool, toolIndex) => (
                          <span key={`${tool.name}-${toolIndex}`}>
                            {tool.name ?? "tool"}{tool.result ? " loaded" : ""}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))
              ) : (
                <div className="dataset-empty">
                  Ask the planning agent about weak categories, evidence, or recommended interventions.
                </div>
              )}
            </div>

            <div className="chat-input-bar">
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
                rows={3}
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
