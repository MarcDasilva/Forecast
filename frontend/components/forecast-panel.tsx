"use client";

import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

type ForecastMode = "time_to_target" | "required_rate";

type ForecastObservedPoint = {
  date: string | null;
  score: number;
  dataset_id: string;
  source_ref: string;
  title: string | null;
  dataset_final_score: number;
  benchmark_eval: number;
  similarity: number;
};

type ForecastPoint = {
  date: string | null;
  predicted: number | null;
  lower_ci: number | null;
  upper_ci: number | null;
  trend: number | null;
  is_historical: boolean;
};

type ForecastSummary = {
  history_points: number;
  projection_history_points?: number;
  history_window_days?: number;
  history_date_basis?: string | null;
  current_score: number;
  last_observed_date: string | null;
  forecast_periods: number;
  target_days?: number | null;
  target_date?: string | null;
  target_reached?: boolean;
  estimated_date?: string | null;
  days_remaining?: number | null;
  last_observed_y?: number | null;
  resolved_target_date?: string | null;
  required_rate_per_day?: number | null;
  prophet_trend_rate?: number | null;
  rate_ratio?: number | null;
  feasibility?: string | null;
};

export type CategoryForecastResponse = {
  category: string;
  mode: ForecastMode;
  target_y: number;
  history_source: string;
  observed_points: ForecastObservedPoint[];
  forecast_points: ForecastPoint[];
  summary: ForecastSummary;
};

type ForecastPanelProps = {
  categoryLabel: string;
  mode: ForecastMode;
  targetY: string;
  targetDate: string;
  forecastPeriods: number;
  data: CategoryForecastResponse | null;
  isLoading: boolean;
  error: string | null;
  onModeChange: (value: ForecastMode) => void;
  onTargetYChange: (value: string) => void;
  onTargetDateChange: (value: string) => void;
  onForecastPeriodsChange: (value: number) => void;
  onGenerate: () => void;
  onClose: () => void;
};

function formatDate(value: string | null | undefined, style: "short" | "long" = "short") {
  if (!value) {
    return "--";
  }

  return new Intl.DateTimeFormat("en-CA", {
    month: style === "long" ? "long" : "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatNumber(value: number | null | undefined, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }

  return value.toFixed(digits);
}

function clampChartValue(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }

  return Math.max(0, Math.min(100, value));
}

function getBadgeVariant(feasibility: string | null | undefined): "default" | "muted" | "success" | "warning" {
  if (!feasibility) {
    return "muted";
  }
  if (feasibility === "on track" || feasibility === "target met") {
    return "success";
  }
  if (feasibility === "aggressive") {
    return "warning";
  }
  return "default";
}

export function ForecastPanel({
  categoryLabel,
  mode,
  targetY,
  targetDate,
  forecastPeriods,
  data,
  isLoading,
  error,
  onModeChange,
  onTargetYChange,
  onTargetDateChange,
  onForecastPeriodsChange,
  onGenerate,
  onClose,
}: ForecastPanelProps) {
  const chartData = useMemo(() => {
    if (!data) {
      return [];
    }

    const observedByDate = new Map(
      data.observed_points.filter((point) => point.date).map((point) => [point.date as string, point]),
    );

    return data.forecast_points
      .filter((point) => point.date)
      .map((point) => {
        const observed = observedByDate.get(point.date as string);
        const lower = clampChartValue(point.lower_ci);
        const upper = clampChartValue(point.upper_ci);
        const predicted = clampChartValue(point.predicted);
        const observedValue = clampChartValue(observed?.score);
        return {
          date: point.date as string,
          fitted: point.is_historical ? predicted : null,
          projected: point.is_historical ? null : predicted,
          observed: observedValue,
          lowerBound: lower,
          confidenceRange:
            typeof lower === "number" && typeof upper === "number" ? Math.max(upper - lower, 0) : null,
          datasetTitle: observed?.title ?? null,
          sourceRef: observed?.source_ref ?? null,
        };
      });
  }, [data]);

  const statCards = useMemo(() => {
    if (!data) {
      return [];
    }

    if (data.mode === "time_to_target") {
      return [
        {
          label: "Current score",
          value: formatNumber(data.summary.current_score),
          hint: `${data.summary.history_points} history points`,
        },
        {
          label: "Target score",
          value: formatNumber(data.target_y),
          hint: "Selected threshold",
        },
        {
          label: "Estimated hit",
          value: data.summary.target_reached ? formatDate(data.summary.estimated_date) : "Not reached",
          hint:
            data.summary.target_reached && data.summary.days_remaining
              ? `${Math.round(data.summary.days_remaining)} days remaining`
              : "Outside current forecast horizon",
        },
      ];
    }

    return [
      {
        label: "Current score",
        value: formatNumber(data.summary.current_score),
        hint: `${data.summary.history_points} history points`,
      },
      {
        label: "Required rate",
        value: `${formatNumber(data.summary.required_rate_per_day, 3)}/day`,
        hint: `Target date ${formatDate(data.summary.resolved_target_date)}`,
      },
      {
        label: "Model trend",
        value: `${formatNumber(data.summary.prophet_trend_rate, 3)}/day`,
        hint:
          data.summary.rate_ratio != null
            ? `${formatNumber(data.summary.rate_ratio, 2)}x current trend`
            : "Trend ratio unavailable",
      },
    ];
  }, [data]);

  return (
    <section className="forecast-stage">
      <div className="forecast-shell">
        <div className="forecast-header">
          <div className="forecast-header-copy">
            <div className="forecast-eyebrow-row">
              <Badge className="forecast-badge" variant="muted">
                Forecast Explorer
              </Badge>
              {data?.summary.feasibility ? (
                <Badge className="forecast-badge" variant={getBadgeVariant(data.summary.feasibility)}>
                  {data.summary.feasibility}
                </Badge>
              ) : null}
            </div>
            <h2 className="forecast-title">{categoryLabel} trajectory forecast</h2>
            <p className="forecast-description">
              Uses the same Prophet-based forecast engine as the forecasting module, mapped onto the
              category&apos;s rolling aggregate score history.
            </p>
          </div>

          <div className="forecast-header-actions">
            <button className="terminal-button forecast-action-button" onClick={onClose} type="button">
              Hide Forecast
            </button>
            <button
              className="terminal-button terminal-button-primary forecast-action-button"
              onClick={onGenerate}
              type="button"
            >
              {isLoading ? "Generating..." : "Generate Forecast"}
            </button>
          </div>
        </div>

        <div className="forecast-content">
          <div className="forecast-chart-grid">
            <div className="forecast-chart-panel">
              <div className="forecast-chart-heading">
                <div>
                  <span className="forecast-label">Chart</span>
                  <strong>Observed score, model fit, and projected path</strong>
                </div>
                {data ? (
                  <span className="forecast-chart-note">Last observed {formatDate(data.summary.last_observed_date)}</span>
                ) : null}
              </div>

              <div className="forecast-chart-shell">
                {isLoading ? (
                  <div className="forecast-empty-state">Generating forecast curve and confidence band...</div>
                ) : error ? (
                  <div className="forecast-empty-state forecast-empty-state-error">{error}</div>
                ) : chartData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ top: 14, right: 18, bottom: 4, left: 0 }}>
                      <defs>
                        <linearGradient id="forecastBand" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0%" stopColor="#ff9d00" stopOpacity={0.24} />
                          <stop offset="100%" stopColor="#ff9d00" stopOpacity={0.02} />
                        </linearGradient>
                        <linearGradient id="forecastProjection" x1="0" x2="1" y1="0" y2="0">
                          <stop offset="0%" stopColor="#ffb341" />
                          <stop offset="100%" stopColor="#ff9d00" />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        stroke="rgba(255, 166, 0, 0.12)"
                        strokeDasharray="3 3"
                        vertical={false}
                      />
                      <XAxis
                        axisLine={false}
                        dataKey="date"
                        minTickGap={32}
                        tick={{ fill: "rgba(255, 217, 138, 0.68)", fontSize: 10 }}
                        tickFormatter={(value) => formatDate(value)}
                        tickLine={false}
                      />
                      <YAxis
                        axisLine={false}
                        domain={[0, 100]}
                        tick={{ fill: "rgba(255, 217, 138, 0.68)", fontSize: 10 }}
                        tickLine={false}
                      />
                      <Tooltip
                        content={({ active, payload, label }) => {
                          if (!active || !payload?.length) {
                            return null;
                          }

                          const observedValue = payload.find((entry) => entry.dataKey === "observed")?.value;
                          const projectedValue =
                            payload.find((entry) => entry.dataKey === "projected")?.value ??
                            payload.find((entry) => entry.dataKey === "fitted")?.value;
                          const item = payload[0]?.payload as {
                            datasetTitle?: string | null;
                            sourceRef?: string | null;
                          };

                          return (
                            <div className="forecast-tooltip">
                              <strong>{formatDate(typeof label === "string" ? label : null, "long")}</strong>
                              <span>
                                Observed {formatNumber(typeof observedValue === "number" ? observedValue : null)}
                              </span>
                              <span>
                                Model {formatNumber(typeof projectedValue === "number" ? projectedValue : null)}
                              </span>
                              {item.datasetTitle ? <span>{item.datasetTitle}</span> : null}
                              {!item.datasetTitle && item.sourceRef ? <span>{item.sourceRef}</span> : null}
                            </div>
                          );
                        }}
                        cursor={{ stroke: "rgba(255, 166, 0, 0.28)", strokeWidth: 1 }}
                      />
                      <Legend
                        verticalAlign="top"
                        wrapperStyle={{
                          color: "rgba(255, 217, 138, 0.8)",
                          fontSize: "11px",
                          paddingBottom: "2px",
                          textTransform: "uppercase",
                        }}
                      />
                      <Area
                        dataKey="lowerBound"
                        fill="transparent"
                        legendType="none"
                        stackId="confidence"
                        stroke="transparent"
                        type="monotone"
                      />
                      <Area
                        dataKey="confidenceRange"
                        fill="url(#forecastBand)"
                        name="Confidence band"
                        stackId="confidence"
                        stroke="transparent"
                        type="monotone"
                      />
                      <Line
                        dataKey="observed"
                        dot={{ fill: "#ffd98a", r: 2.5, strokeWidth: 0 }}
                        name="Observed"
                        stroke="#ffd98a"
                        strokeWidth={1.8}
                        type="monotone"
                      />
                      <Line
                        dataKey="fitted"
                        dot={false}
                        name="Model fit"
                        stroke="rgba(255, 157, 0, 0.7)"
                        strokeWidth={1.6}
                        type="monotone"
                      />
                      <Line
                        dataKey="projected"
                        dot={false}
                        name="Projection"
                        stroke="url(#forecastProjection)"
                        strokeDasharray="5 4"
                        strokeWidth={2.4}
                        type="monotone"
                      />
                      <ReferenceLine
                        label={{
                          fill: "rgba(255, 217, 138, 0.72)",
                          fontSize: 10,
                          position: "insideTopRight",
                          value: "target",
                        }}
                        stroke="rgba(255, 166, 0, 0.58)"
                        strokeDasharray="4 4"
                        y={data?.target_y ?? Number(targetY)}
                      />
                      {data?.summary.last_observed_date ? (
                        <ReferenceLine
                          label={{
                            fill: "rgba(182, 141, 65, 0.95)",
                            fontSize: 10,
                            position: "insideTopLeft",
                            value: "last obs",
                          }}
                          stroke="rgba(255, 166, 0, 0.16)"
                          x={data.summary.last_observed_date}
                        />
                      ) : null}
                    </ComposedChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="forecast-empty-state">
                    Open the forecast with at least two completed observations for this category.
                  </div>
                )}
              </div>
            </div>

            <aside className="forecast-insights">
              <section className="forecast-insight-card">
                <div className="forecast-insight-header">
                  <strong>Controls</strong>
                </div>
                <div className="forecast-insight-body">
                  <div className="forecast-control-group">
                    <span className="forecast-label">Mode</span>
                    <div className="forecast-button-row">
                      <button
                        className={`forecast-toggle${mode === "time_to_target" ? " forecast-toggle-active" : ""}`}
                        onClick={() => onModeChange("time_to_target")}
                        type="button"
                      >
                        Time To Target
                      </button>
                      <button
                        className={`forecast-toggle${mode === "required_rate" ? " forecast-toggle-active" : ""}`}
                        onClick={() => onModeChange("required_rate")}
                        type="button"
                      >
                        Required Rate
                      </button>
                    </div>
                  </div>

                  <label className="forecast-control-group">
                    <span className="forecast-label">Target score</span>
                    <Input
                      className="forecast-input"
                      inputMode="decimal"
                      max={100}
                      min={0}
                      onChange={(event) => onTargetYChange(event.target.value)}
                      step="0.5"
                      type="number"
                      value={targetY}
                    />
                  </label>

                  {mode === "required_rate" ? (
                    <label className="forecast-control-group">
                      <span className="forecast-label">Target date</span>
                      <Input
                        className="forecast-input"
                        onChange={(event) => onTargetDateChange(event.target.value)}
                        type="date"
                        value={targetDate}
                      />
                    </label>
                  ) : null}

                  <div className="forecast-control-group">
                    <span className="forecast-label">Horizon</span>
                    <div className="forecast-button-row">
                      {[180, 365, 730].map((days) => (
                        <button
                          key={days}
                          className={`forecast-chip${forecastPeriods === days ? " forecast-chip-active" : ""}`}
                          onClick={() => onForecastPeriodsChange(days)}
                          type="button"
                        >
                          {days === 180 ? "6M" : days === 365 ? "1Y" : "2Y"}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              <section className="forecast-insight-card">
                <div className="forecast-insight-header">
                  <strong>Forecast Readout</strong>
                </div>
                <div className="forecast-insight-body forecast-stat-grid">
                  {statCards.map((card) => (
                    <div key={card.label} className="forecast-stat-card">
                      <span className="forecast-stat-label">{card.label}</span>
                      <strong className="forecast-stat-value">{card.value}</strong>
                      <p className="forecast-stat-hint">{card.hint}</p>
                    </div>
                  ))}

                  <div className="forecast-insight-list">
                    <div>
                      <span className="forecast-label">Input series</span>
                      <p>{data?.history_source ?? "Waiting for forecast data."}</p>
                    </div>
                    <div>
                      <span className="forecast-label">Observed window</span>
                      <p>
                        {data
                          ? `${data.summary.history_points} score snapshots / ${data.summary.projection_history_points ?? "--"} projected history points`
                          : "--"}
                      </p>
                    </div>
                    <div>
                      <span className="forecast-label">History span</span>
                      <p>
                        {data?.summary.history_window_days
                          ? `${Math.round(data.summary.history_window_days / 365)} years`
                          : "--"}
                      </p>
                    </div>
                    <div>
                      <span className="forecast-label">Forecast horizon</span>
                      <p>{forecastPeriods} days</p>
                    </div>
                    <div>
                      <span className="forecast-label">Mode output</span>
                      <p>
                        {data?.mode === "required_rate"
                          ? "Required daily lift versus modeled trend"
                          : "First projected date that reaches the selected target"}
                      </p>
                    </div>
                  </div>

                  {data ? (
                    <div className="forecast-insight-list">
                      {data.mode === "required_rate" ? (
                        <>
                          <div>
                            <span className="forecast-label">Feasibility</span>
                            <p>{data.summary.feasibility ?? "--"}</p>
                          </div>
                          <div>
                            <span className="forecast-label">Modeled ratio</span>
                            <p>{formatNumber(data.summary.rate_ratio, 2)}x current trend</p>
                          </div>
                          <div>
                            <span className="forecast-label">Deadline</span>
                            <p>{formatDate(data.summary.resolved_target_date)}</p>
                          </div>
                        </>
                      ) : (
                        <>
                          <div>
                            <span className="forecast-label">Target reached</span>
                            <p>{data.summary.target_reached ? "Yes, within horizon" : "No, not within horizon"}</p>
                          </div>
                          <div>
                            <span className="forecast-label">Estimated date</span>
                            <p>{formatDate(data.summary.estimated_date)}</p>
                          </div>
                          <div>
                            <span className="forecast-label">Remaining time</span>
                            <p>
                              {data.summary.days_remaining != null
                                ? `${Math.round(data.summary.days_remaining)} days`
                                : "Increase horizon to continue exploring"}
                            </p>
                          </div>
                        </>
                      )}
                    </div>
                  ) : (
                    <div className="forecast-empty-state">
                      Generate a forecast to see the mode-specific interpretation.
                    </div>
                  )}
                </div>
              </section>
            </aside>
          </div>
        </div>
      </div>
    </section>
  );
}
