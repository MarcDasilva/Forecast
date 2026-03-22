#!/usr/bin/env python3
"""
Integration smoke tests for the FRED MCP HTTP server.

This script follows the workflow recommended in agent_server_guide.md
for Canada-focused macro context:
1. Initialize an MCP session
2. List available tools
3. Use fred_search for Canada-focused discovery
4. Use fred_get_series for Canada-focused retrieval
5. Use fred_browse only as a fallback / smoke test

Run with:
    python test_agent_tool_calls.py

Optional environment variables:
    FRED_MCP_URL=http://localhost:3000/mcp
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from typing import Any


DEFAULT_MCP_URL = "http://localhost:3000/mcp"
PROTOCOL_VERSION = "2024-11-05"


def print_json(title: str, payload: Any) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2))


class MCPHttpClient:
    def __init__(self, url: str) -> None:
        self.url = url
        self.session_id: str | None = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        include_session: bool,
        include_id: bool = True,
    ) -> tuple[dict[str, Any], Any]:
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

        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                data = json.loads(body) if body else {}
                return data, response
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AssertionError(
                f"MCP request failed: method={method}, status={exc.code}, body={body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise AssertionError(
                f"Could not reach MCP server at {self.url}. "
                "Start it with `node build/index.js --http` first."
            ) from exc

    def initialize(self) -> dict[str, Any]:
        data, response = self._post(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "python-agent-test",
                    "version": "1.0.0",
                },
            },
            include_session=False,
        )

        self.session_id = response.headers.get("mcp-session-id")
        if not self.session_id:
            raise AssertionError("Initialize response did not include mcp-session-id")

        self._post(
            "notifications/initialized",
            include_session=True,
            include_id=False,
        )
        return data

    def list_tools(self) -> dict[str, Any]:
        data, _ = self._post("tools/list", include_session=True)
        return data

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        data, _ = self._post(
            "tools/call",
            {"name": name, "arguments": arguments},
            include_session=True,
        )
        return data


def extract_text_payload(response: dict[str, Any]) -> Any:
    result = response.get("result", {})
    content = result.get("content", [])
    if not content:
        raise AssertionError(f"Tool response had no content: {response}")

    first = content[0]
    if first.get("type") != "text":
        raise AssertionError(f"Expected first content item to be text: {response}")

    text = first.get("text", "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


class TestAgentToolCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = MCPHttpClient(os.environ.get("FRED_MCP_URL", DEFAULT_MCP_URL))
        cls.initialize_response = cls.client.initialize()

    def test_initialize_returns_server_info(self) -> None:
        result = self.initialize_response.get("result", {})
        server_info = result.get("serverInfo", {})
        self.assertEqual(server_info.get("name"), "fred")
        self.assertTrue(self.client.session_id)
        print_json(
            "Initialize Response",
            {
                "serverInfo": server_info,
                "session_id": self.client.session_id,
            },
        )

    def test_list_tools_includes_core_agent_tools(self) -> None:
        response = self.client.list_tools()
        tools = response.get("result", {}).get("tools", [])
        tool_names = {tool["name"] for tool in tools}

        self.assertIn("fred_search", tool_names)
        self.assertIn("fred_get_series", tool_names)
        self.assertIn("fred_browse", tool_names)
        print_json("Available Tools", sorted(tool_names))

    def test_agent_workflow_search_then_get_series(self) -> None:
        search_response = self.client.call_tool(
            "fred_search",
            {
                "search_text": "Canada unemployment",
                "search_type": "full_text",
                "limit": 5,
                "order_by": "popularity",
                "sort_order": "desc",
            },
        )
        search_data = extract_text_payload(search_response)

        self.assertIsInstance(search_data, dict)
        self.assertIn("results", search_data)
        self.assertGreater(len(search_data["results"]), 0)

        canada_results = [
            result
            for result in search_data["results"]
            if "canada" in json.dumps(result).lower()
        ]
        self.assertGreater(
            len(canada_results),
            0,
            f"No Canada-focused results found in search output: {search_data['results']}",
        )
        print_json(
            "Search Sample",
            {
                "count": search_data.get("count"),
                "first_results": canada_results[:3],
            },
        )

        best_match = canada_results[0]
        series_id = best_match.get("series_id") or best_match.get("id")
        self.assertTrue(series_id, f"Search result missing series_id: {best_match}")

        series_response = self.client.call_tool(
            "fred_get_series",
            {
                "series_id": series_id,
                "observation_start": "2020-01-01",
                "sort_order": "asc",
                "units": "lin",
                "limit": 24,
            },
        )
        series_data = extract_text_payload(series_response)

        self.assertIsInstance(series_data, dict)
        self.assertEqual(series_data.get("series_id"), series_id)
        self.assertIn("data", series_data)
        self.assertGreater(len(series_data["data"]), 0)

        first_observation = series_data["data"][0]
        self.assertIn("date", first_observation)
        self.assertIn("value", first_observation)
        print_json(
            "Retrieved Series Sample",
            {
                "series_id": series_data.get("series_id"),
                "title": series_data.get("title"),
                "units": series_data.get("units"),
                "sample_observations": series_data["data"][:5],
            },
        )

    def test_known_series_retrieval_for_trend_feature(self) -> None:
        response = self.client.call_tool(
            "fred_get_series",
            {
                "series_id": "CPALCY01CAM661N",
                "observation_start": "2018-01-01",
                "sort_order": "asc",
                "units": "lin",
                "frequency": "m",
                "limit": 24,
            },
        )
        data = extract_text_payload(response)

        self.assertIsInstance(data, dict)
        self.assertEqual(data.get("series_id"), "CPALCY01CAM661N")
        self.assertIn("data", data)
        self.assertGreater(len(data["data"]), 0)
        print_json(
            "Canada CPI Sample",
            {
                "series_id": data.get("series_id"),
                "title": data.get("title"),
                "units": data.get("units"),
                "sample_observations": data["data"][:5],
            },
        )

    def test_browse_smoke_test_for_fallback_discovery(self) -> None:
        response = self.client.call_tool(
            "fred_browse",
            {
                "browse_type": "categories",
                "limit": 5,
            },
        )
        data = extract_text_payload(response)

        self.assertIsInstance(data, dict)
        self.assertIn("categories", data)
        self.assertGreater(len(data["categories"]), 0)
        print_json("Browse Sample", data["categories"][:5])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestAgentToolCalls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
