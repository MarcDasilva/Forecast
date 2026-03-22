from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from langsmith import trace, traceable

from forecast.config import Settings, get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_VERSION = "2024-11-05"
REQUIRED_FRED_TOOLS = {"fred_browse", "fred_get_series", "fred_search"}
EMPLOYMENT_SERIES_QUERIES = (
    {
        "indicator": "canada_unemployment_rate",
        "search_text": "Canada unemployment rate total",
        "preferred_terms": ("canada", "unemployment", "total"),
        "disallowed_terms": ("youth", "15 to 24", "15-24"),
        "observation_start": "2022-01-01",
    },
    {
        "indicator": "canada_labour_force_participation_rate",
        "search_text": "Canada labour force participation rate",
        "preferred_terms": ("canada", "participation", "total"),
        "disallowed_terms": (),
        "observation_start": "2022-01-01",
    },
)


def _format_number(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:.2f}".rstrip("0").rstrip(".")


class FredMcpHttpClient:
    def __init__(self, *, url: str, timeout_seconds: float = 30.0) -> None:
        self.url = url
        self._request_id = 0
        self.session_id: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def __aenter__(self) -> FredMcpHttpClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _post(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        include_session: bool,
        include_id: bool = True,
    ) -> tuple[dict[str, Any], httpx.Response]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if include_id:
            payload["id"] = self._next_id()
        if params is not None:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if include_session and self.session_id:
            headers["mcp-session-id"] = self.session_id

        response = await self._client.post(self.url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json() if response.content else {}
        if "error" in data:
            error = data["error"]
            raise RuntimeError(
                f"MCP request failed for {method}: "
                f"{error.get('code')} {error.get('message')}"
            )
        return data, response

    async def initialize(self) -> dict[str, Any]:
        data, response = await self._post(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "forecast-employment-specialist",
                    "version": "1.0.0",
                },
            },
            include_session=False,
        )
        self.session_id = response.headers.get("mcp-session-id")
        if not self.session_id:
            raise RuntimeError("Initialize response did not include mcp-session-id")

        await self._post(
            "notifications/initialized",
            include_session=True,
            include_id=False,
        )
        return data

    async def ensure_initialized(self) -> None:
        if not self.session_id:
            await self.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.ensure_initialized()
        data, _ = await self._post("tools/list", include_session=True)
        return data.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        await self.ensure_initialized()
        data, _ = await self._post(
            "tools/call",
            {"name": name, "arguments": arguments},
            include_session=True,
        )
        return data

    async def call_tool_json(self, name: str, arguments: dict[str, Any]) -> Any:
        data = await self.call_tool(name, arguments)
        result = data.get("result", {})
        content = result.get("content", [])
        if not content:
            raise RuntimeError(f"Tool {name} returned no content")

        first = content[0]
        text = first.get("text", "")
        if result.get("isError"):
            raise RuntimeError(text or f"Tool {name} returned an error")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


class FredMcpServerManager:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def _server_dir(self) -> Path:
        configured = Path(self.settings.fred_mcp_server_dir)
        if configured.is_absolute():
            return configured
        return PROJECT_ROOT / configured

    @property
    def _server_entrypoint(self) -> Path:
        return self._server_dir / "build" / "index.js"

    async def ensure_running(self) -> None:
        if await self._can_initialize():
            return

        if not self.settings.fred_mcp_auto_start:
            raise RuntimeError(
                f"FRED MCP server is not reachable at {self.settings.fred_mcp_url}"
            )

        parsed = urlparse(self.settings.fred_mcp_url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise RuntimeError(
                "Automatic FRED MCP startup only supports localhost URLs"
            )

        if not self._server_entrypoint.exists():
            raise FileNotFoundError(
                "FRED MCP server build artifact is missing. "
                "Run `npm install && npm run build` in fred-mcp-server-main."
            )

        env = os.environ.copy()
        env["PORT"] = str(parsed.port or 3010)
        env["TRANSPORT"] = "http"
        if self.settings.fred_api_key:
            env["FRED_API_KEY"] = self.settings.fred_api_key.get_secret_value()

        process = subprocess.Popen(
            ["node", "build/index.js", "--http"],
            cwd=self._server_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        deadline = asyncio.get_running_loop().time() + self.settings.fred_mcp_start_timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            if await self._can_initialize():
                return
            if process.poll() is not None:
                break
            await asyncio.sleep(0.5)

        raise RuntimeError(
            f"Failed to start FRED MCP server at {self.settings.fred_mcp_url}"
        )

    async def _can_initialize(self) -> bool:
        try:
            async with FredMcpHttpClient(url=self.settings.fred_mcp_url, timeout_seconds=5.0) as client:
                await client.initialize()
            return True
        except Exception:
            return False

    async def restart_local_server(self) -> None:
        parsed = urlparse(self.settings.fred_mcp_url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise RuntimeError("Automatic restart only supports localhost FRED MCP URLs")

        for pid in self._list_listening_pids(parsed.port or 3010):
            if self._is_fred_server_process(pid):
                os.kill(pid, signal.SIGTERM)

        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            if not await self._can_initialize():
                break
            await asyncio.sleep(0.25)

        await self.ensure_running()

    def _list_listening_pids(self, port: int) -> list[int]:
        result = subprocess.run(
            ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN", "-n", "-P"],
            capture_output=True,
            check=False,
            text=True,
        )
        return [
            int(line.strip())
            for line in result.stdout.splitlines()
            if line.strip().isdigit()
        ]

    def _is_fred_server_process(self, pid: int) -> bool:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            check=False,
            text=True,
        )
        command = result.stdout.strip()
        return "build/index.js" in command and "--http" in command


class EmploymentMacroContextProvider:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        server_manager: FredMcpServerManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.server_manager = server_manager or FredMcpServerManager(settings=self.settings)

    @traceable(
        name="employment_fred_macro_context",
        run_type="chain",
        tags=["employment", "fred", "mcp"],
    )
    async def build_context(self) -> dict[str, Any]:
        return await self._build_context(allow_restart=True)

    async def _build_context(self, *, allow_restart: bool) -> dict[str, Any]:
        fallback = {
            "source": "fred_mcp",
            "available": False,
            "server_url": self.settings.fred_mcp_url,
            "tool_calls": [],
            "indicators": [],
            "summary_lines": [],
            "errors": [],
        }

        if not self.settings.fred_mcp_enabled:
            fallback["errors"].append("FRED MCP integration is disabled.")
            return fallback

        try:
            await self.server_manager.ensure_running()

            async with FredMcpHttpClient(url=self.settings.fred_mcp_url) as client:
                tools = await self._call_fred_tool(
                    client,
                    tool_name="tools/list",
                    arguments={},
                )
                tool_names = {tool["name"] for tool in tools}
                missing_tools = sorted(REQUIRED_FRED_TOOLS - tool_names)
                if missing_tools:
                    raise RuntimeError(
                        "FRED MCP server is missing required tools: "
                        + ", ".join(missing_tools)
                    )

                tool_calls: list[dict[str, Any]] = [
                    {
                        "name": "tools/list",
                        "ok": True,
                        "tools": sorted(tool_names),
                    }
                ]
                indicators: list[dict[str, Any]] = []
                summary_lines: list[str] = []
                errors: list[str] = []

                for query in EMPLOYMENT_SERIES_QUERIES:
                    search_args = {
                        "search_text": query["search_text"],
                        "search_type": "full_text",
                        "limit": 5,
                        "order_by": "popularity",
                        "sort_order": "desc",
                    }

                    try:
                        search_data = await self._call_fred_tool(
                            client,
                            tool_name="fred_search",
                            arguments=search_args,
                        )
                        results = search_data.get("results", [])
                        selected = self._select_best_result(
                            results,
                            preferred_terms=query["preferred_terms"],
                            disallowed_terms=query.get("disallowed_terms", ()),
                        )
                        if not selected:
                            message = (
                                f"{query['indicator']}: no matching FRED series found "
                                f"for {query['search_text']!r}"
                            )
                            tool_calls.append(
                                {
                                    "name": "fred_search",
                                    "ok": False,
                                    "indicator": query["indicator"],
                                    "arguments": search_args,
                                    "error": message,
                                }
                            )
                            errors.append(message)
                            continue

                        series_id = selected.get("id")
                        tool_calls.append(
                            {
                                "name": "fred_search",
                                "ok": True,
                                "indicator": query["indicator"],
                                "arguments": search_args,
                                "selected_series_id": series_id,
                                "selected_title": selected.get("title"),
                            }
                        )

                        series_args = {
                            "series_id": series_id,
                            "observation_start": query["observation_start"],
                            "sort_order": "asc",
                            "units": "lin",
                            "limit": 24,
                        }
                        series_data = await self._call_fred_tool(
                            client,
                            tool_name="fred_get_series",
                            arguments=series_args,
                        )
                        indicator = self._summarize_series(query["indicator"], selected, series_data)
                        indicators.append(indicator)
                        summary_lines.append(indicator["summary"])
                        tool_calls.append(
                            {
                                "name": "fred_get_series",
                                "ok": True,
                                "indicator": query["indicator"],
                                "arguments": series_args,
                                "latest_date": indicator.get("latest_date"),
                                "latest_value": indicator.get("latest_value"),
                            }
                        )
                    except Exception as exc:
                        if allow_restart and self._should_restart_for_invalid_key(exc):
                            await self.server_manager.restart_local_server()
                            return await self._build_context(allow_restart=False)
                        message = f"{query['indicator']}: {exc}"
                        tool_calls.append(
                            {
                                "name": "fred_search",
                                "ok": False,
                                "indicator": query["indicator"],
                                "arguments": search_args,
                                "error": str(exc),
                            }
                        )
                        errors.append(message)

                return {
                    "source": "fred_mcp",
                    "available": bool(indicators),
                    "server_url": self.settings.fred_mcp_url,
                    "tool_calls": tool_calls,
                    "indicators": indicators,
                    "summary_lines": summary_lines,
                    "errors": errors[:5],
                }
        except Exception as exc:
            fallback["errors"].append(str(exc))
            return fallback

    def _should_restart_for_invalid_key(self, exc: Exception) -> bool:
        if not self.settings.fred_api_key:
            return False
        message = str(exc).lower()
        return "api_key" in message and "not registered" in message

    async def _call_fred_tool(
        self,
        client: FredMcpHttpClient,
        *,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        async with trace(
            f"employment_{tool_name}",
            run_type="tool",
            inputs={
                "tool_name": tool_name,
                "arguments": arguments,
                "server_url": self.settings.fred_mcp_url,
            },
            tags=["employment", "fred", "mcp"],
            metadata={"category": "employment"},
        ) as run:
            if tool_name == "tools/list":
                result = await client.list_tools()
                run.end(
                    outputs={
                        "tool_names": sorted(tool["name"] for tool in result),
                        "tool_count": len(result),
                    }
                )
                return result

            result = await client.call_tool_json(tool_name, arguments)
            run.end(outputs={"result_preview": self._preview_tool_result(result)})
            return result

    def _preview_tool_result(self, result: Any) -> Any:
        if isinstance(result, dict):
            if "results" in result:
                return {
                    "result_count": len(result.get("results", [])),
                    "first_result": result.get("results", [])[:1],
                }
            if "data" in result:
                return {
                    "series_id": result.get("series_id"),
                    "title": result.get("title"),
                    "data_points": len(result.get("data", [])),
                    "latest_observation": result.get("data", [])[-1:] if result.get("data") else [],
                }
        return result

    def _select_best_result(
        self,
        results: list[dict[str, Any]],
        *,
        preferred_terms: tuple[str, ...],
        disallowed_terms: tuple[str, ...],
    ) -> dict[str, Any] | None:
        if not results:
            return None

        def score(result: dict[str, Any]) -> tuple[float, int]:
            title = str(result.get("title", "")).lower()
            notes = str(result.get("notes", "")).lower()
            units = str(result.get("units", "")).lower()
            frequency = str(result.get("frequency", "")).lower()
            seasonal_adjustment = str(result.get("seasonal_adjustment", "")).lower()

            title_hits = sum(term in title for term in preferred_terms)
            notes_hits = sum(term in notes for term in preferred_terms)
            disallowed_hits = sum(
                term in title or term in notes for term in disallowed_terms
            )
            percent_bonus = 1 if "percent" in units else 0
            monthly_bonus = 4 if "monthly" in frequency else 0
            seasonally_adjusted_bonus = 3 if "seasonally adjusted" in seasonal_adjustment else 0
            popularity = int(result.get("popularity", 0) or 0)
            return (
                title_hits * 10
                + notes_hits
                + percent_bonus
                + monthly_bonus
                + seasonally_adjusted_bonus
                - disallowed_hits * 20,
                popularity,
            )

        return max(results, key=score)

    def _summarize_series(
        self,
        indicator_name: str,
        selected_result: dict[str, Any],
        series_data: dict[str, Any],
    ) -> dict[str, Any]:
        observations = [
            observation
            for observation in series_data.get("data", [])
            if observation.get("value") is not None
        ]
        latest = observations[-1] if observations else None
        previous = observations[-2] if len(observations) > 1 else None

        latest_value = latest.get("value") if latest else None
        previous_value = previous.get("value") if previous else None
        delta = None
        if latest_value is not None and previous_value is not None:
            delta = round(latest_value - previous_value, 2)

        latest_formatted = _format_number(latest_value)
        previous_formatted = _format_number(previous_value)
        delta_formatted = _format_number(abs(delta) if delta is not None else None)
        direction = "up" if delta and delta > 0 else "down" if delta and delta < 0 else "flat"

        summary = (
            f"{series_data.get('title', selected_result.get('title'))} "
            f"({series_data.get('series_id', selected_result.get('id'))}) "
            f"latest {latest_formatted or 'n/a'} on {latest.get('date') if latest else 'n/a'}"
        )
        if previous and delta_formatted is not None:
            summary += (
                f", previous {previous_formatted} on {previous.get('date')} "
                f"({direction} {delta_formatted})."
            )
        else:
            summary += "."

        return {
            "indicator": indicator_name,
            "series_id": series_data.get("series_id", selected_result.get("id")),
            "title": series_data.get("title", selected_result.get("title")),
            "units": series_data.get("units", selected_result.get("units")),
            "frequency": series_data.get("frequency", selected_result.get("frequency")),
            "latest_date": latest.get("date") if latest else None,
            "latest_value": latest_value,
            "previous_date": previous.get("date") if previous else None,
            "previous_value": previous_value,
            "delta": delta,
            "summary": summary,
        }
