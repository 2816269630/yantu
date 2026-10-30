"""Small server-side boundary to Plane's documented public API."""

from html import escape
import logging
from urllib.parse import quote

import httpx

from .models import Team

logger = logging.getLogger(__name__)


class PlaneError(Exception):
    pass


class PlaneClient:
    def __init__(self, base_url: str, api_key: str, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.transport = transport

    def configured(self, team: Team) -> bool:
        return bool(self.base_url and self.api_key and team.plane_workspace_slug and team.plane_project_id)

    def _path(self, team: Team, tail: str) -> str:
        slug = quote(team.plane_workspace_slug or "", safe="")
        project = quote(team.plane_project_id or "", safe="")
        return f"{self.base_url}/api/v1/workspaces/{slug}/projects/{project}/{tail}"

    def _request(self, method: str, url: str, accept_conflict: bool = False, **kwargs):
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                result = client.request(method, url, headers={"X-API-Key": self.api_key}, **kwargs)
                if not (accept_conflict and result.status_code == 409):
                    result.raise_for_status()
                if result.status_code == 204:
                    return {}
                return result.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("Plane %s request failed: %s", method, type(error).__name__)
            raise PlaneError("Plane 服务暂时不可用，请检查项目绑定和 API Key") from error

    def list_work_items(self, team: Team, cursor: str | None = None) -> dict:
        if not self.configured(team):
            raise PlaneError("该课题组尚未绑定 Plane 项目")
        params = {"per_page": 100, "expand": "state"}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", self._path(team, "work-items/"), params=params)

    def _items(self, team: Team, tail: str, params: dict | None = None):
        query = {"per_page": 100, **(params or {})}
        seen = set()
        for _ in range(100):
            page = self._request("GET", self._path(team, tail), params=query)
            if isinstance(page, list):
                yield from page
                return
            if not isinstance(page, dict) or not isinstance(page.get("results"), list):
                raise PlaneError("Plane 返回了无法识别的列表")
            yield from page["results"]
            if not page.get("next_page_results"):
                return
            cursor = page.get("next_cursor")
            if not cursor or cursor in seen:
                raise PlaneError("Plane 分页异常，请稍后重试")
            seen.add(cursor)
            query["cursor"] = cursor
        raise PlaneError("Plane 数据较多，本次同步未完成，请缩小项目范围")

    def list_allowed_projects(self, allowed: str) -> list[dict]:
        if not self.base_url or not self.api_key:
            return []
        projects = []
        for entry in dict.fromkeys(part.strip() for part in allowed.split(",") if part.strip()):
            slug, separator, project_id = entry.partition(":")
            if not separator or not slug or not project_id:
                continue
            team = Team(plane_workspace_slug=slug, plane_project_id=project_id)
            project = self._request("GET", self._path(team, ""))
            projects.append({"id": project_id, "name": project.get("name", project_id),
                             "workspaceSlug": slug, "workspaceName": slug})
        return projects

    def create_work_item(self, team: Team, title: str, description: str, external_id: str | None = None) -> str | None:
        if not self.configured(team):
            return None
        if external_id:
            for item in self._items(team, "work-items/", {"external_id": external_id,
                                    "external_source": "yantu", "fields": "id,external_id,external_source"}):
                if item.get("external_id") == external_id and item.get("external_source") == "yantu":
                    return str(item["id"])
        body = {"name": title, "description_html": self._html(description)}
        if external_id:
            body.update({"external_id": external_id, "external_source": "yantu"})
        data = self._request(
            "POST",
            self._path(team, "work-items/"),
            accept_conflict=bool(external_id),
            json=body,
        )
        if not isinstance(data, dict) or not data.get("id"):
            raise PlaneError("Plane 创建任务后未返回任务 ID")
        return str(data["id"])

    @staticmethod
    def _html(text: str) -> str:
        return "<p>" + escape(text).replace("\n", "<br>") + "</p>"

    def update_work_item(self, team: Team, work_item_id: str, title: str, description: str,
                         status: str, priority: str = "none", due_at=None) -> None:
        if not self.configured(team) or not work_item_id:
            return
        groups = {"todo": "unstarted", "doing": "started", "blocked": "started",
                  "review": "started", "done": "completed"}
        group = groups.get(status)
        if group is None:
            raise PlaneError("不支持的科研任务状态")
        states = list(self._items(team, "states/"))
        matching = [s for s in states if s.get("group") == group]
        if not matching and status == "todo":
            matching = [s for s in states if s.get("group") == "backlog"]
        if not matching:
            raise PlaneError("Plane 项目缺少对应状态，请在 Plane 中配置任务状态")
        matching.sort(key=lambda s: (not bool(s.get("default")), s.get("sequence", 0), s["id"]))
        target_date = due_at.isoformat()[:10] if hasattr(due_at, "isoformat") else str(due_at)[:10] if due_at else None
        self._request("PATCH", self._path(team, f"work-items/{quote(work_item_id, safe='')}/"),
                      json={"name": title, "description_html": self._html(description),
                            "state": matching[0]["id"], "target_date": target_date,
                            "priority": priority if priority in ("urgent", "high", "medium", "low", "none") else "none"})

    def add_comment(self, team: Team, work_item_id: str | None, content: str) -> None:
        if not self.configured(team) or not work_item_id:
            return
        item = quote(work_item_id, safe="")
        self._request(
            "POST",
            self._path(team, f"work-items/{item}/comments/"),
            json={"comment_html": f"<p>{escape(content)}</p>"},
        )
