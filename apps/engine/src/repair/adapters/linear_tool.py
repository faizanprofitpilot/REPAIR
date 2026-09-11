"""Linear actions via One GraphQL actions (full action IDs required)."""

from __future__ import annotations

from typing import Any

from repair.adapters.one import OneAdapter
from repair.models import ToolResponse

# Full action IDs from `one actions search` (do not truncate — trailing chars are significant)
LINEAR_LIST_TEAMS = "conn_mod_def::GJ4vO-Ddh7M::KSYGS5jiTo66YMeRWLjeSQ"
LINEAR_CREATE_ISSUE = "conn_mod_def::GJ4vJJJqwWo::nUMJLIhORKaqb57y36SEjw"
# Reuse create-issue action endpoint style for arbitrary GraphQL when needed:
LINEAR_GRAPHQL_FETCH = "conn_mod_def::GJ4vGUFHurQ::XHm9MWyaROC_DFHVFcCF9A"

TEAMS_QUERY = "query { teams { nodes { id key name } } }"

ISSUE_CREATE = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url description createdAt }
  }
}
"""

ISSUES_BY_DESCRIPTION = """
query IssuesByDescription($filter: IssueFilter, $first: Int) {
  issues(filter: $filter, first: $first) {
    nodes { id identifier title url description createdAt }
  }
}
"""


class LinearTool:
    def __init__(self, one: OneAdapter) -> None:
        self.one = one

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> ToolResponse:
        data: dict[str, Any] = {"query": query}
        if variables is not None:
            data["variables"] = variables
        # Prefer dedicated actions when recognizable; else natural-language fetchData action
        return self.one.execute_action("linear", LINEAR_GRAPHQL_FETCH, data=data)

    def list_teams(self) -> ToolResponse:
        return self.one.execute_action(
            "linear",
            LINEAR_LIST_TEAMS,
            data={"query": TEAMS_QUERY},
        )

    def resolve_team_id(self, team_key: str | None = None) -> str:
        resp = self.list_teams()
        if not resp.ok:
            raise RuntimeError(f"Linear teams query failed: {resp.error} {resp.body}")
        nodes = (((resp.body or {}).get("data") or {}).get("teams") or {}).get("nodes") or []
        if not nodes:
            raise RuntimeError(f"No Linear teams available: {resp.body}")
        if team_key:
            for n in nodes:
                if n.get("key") == team_key or n.get("name") == team_key:
                    return n["id"]
            raise RuntimeError(f"Linear team not found: {team_key}")
        return nodes[0]["id"]

    def create_issue(
        self,
        *,
        team_id: str,
        title: str,
        description: str,
        priority: int = 1,
    ) -> ToolResponse:
        return self.one.execute_action(
            "linear",
            LINEAR_CREATE_ISSUE,
            data={
                "query": ISSUE_CREATE,
                "variables": {
                    "input": {
                        "teamId": team_id,
                        "title": title,
                        "description": description,
                        "priority": priority,
                    }
                },
            },
        )

    def find_issues_by_marker(self, marker: str, first: int = 5) -> ToolResponse:
        # Use list-teams-style graphql action isn't right; use fetchData / create action endpoint with query
        # Try CREATE action's sibling — use GRAPHQL_FETCH for reads
        resp = self.one.execute_action(
            "linear",
            LINEAR_GRAPHQL_FETCH,
            data={
                "query": ISSUES_BY_DESCRIPTION,
                "variables": {
                    "filter": {"description": {"contains": marker}},
                    "first": first,
                },
            },
        )
        if resp.ok:
            return resp
        # Fallback: reuse list teams action id pattern won't work; try create issue action with query only
        return self.one.execute_action(
            "linear",
            LINEAR_LIST_TEAMS,
            data={
                "query": ISSUES_BY_DESCRIPTION,
                "variables": {
                    "filter": {"description": {"contains": marker}},
                    "first": first,
                },
            },
        )
