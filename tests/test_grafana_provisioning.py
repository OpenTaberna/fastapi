"""
Static checks on the Grafana provisioning files.

The datasource and the dashboard are provisioned from separate files, and the
only thing tying them together is a uid string. Nothing at build or start time
verifies they agree — Grafana provisions both without complaint and every panel
renders "No data", which looks exactly like a shop with no traffic.

That happened. These checks are cheap, need no running stack, and would have
caught it.
"""

import json
from pathlib import Path

import pytest

OBSERVABILITY = Path(__file__).resolve().parent.parent / "src" / "docker" / "observability"
DATASOURCES = OBSERVABILITY / "grafana" / "datasources"
DASHBOARDS = OBSERVABILITY / "grafana" / "dashboards"


def _dashboard_files() -> list[Path]:
    return [p for p in DASHBOARDS.glob("*.json")]


def _datasource_uids() -> set[str]:
    """
    uids declared in the datasource YAML.

    Parsed by hand rather than with PyYAML: the file is a fixed shape and this
    keeps the test suite from gaining a dependency for one assertion.
    """
    uids = set()
    for path in DATASOURCES.glob("*.yml"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("uid:"):
                uids.add(stripped.split(":", 1)[1].strip())
    return uids


def _panel_datasource_uids(dashboard: dict) -> set[str]:
    uids = set()

    def walk(node):
        if isinstance(node, dict):
            datasource = node.get("datasource")
            if isinstance(datasource, dict) and datasource.get("uid"):
                uids.add(datasource["uid"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(dashboard)
    return uids


def test_provisioning_files_exist():
    assert DATASOURCES.is_dir(), "datasource provisioning directory is missing"
    assert _dashboard_files(), "no dashboards to provision"


def test_the_datasource_declares_an_explicit_uid():
    """
    Without one Grafana generates a random uid on first provision, and every
    panel referencing a fixed string resolves to nothing.
    """
    assert _datasource_uids(), (
        "no datasource declares a uid; panels cannot reference it reliably"
    )


@pytest.mark.parametrize("path", _dashboard_files(), ids=lambda p: p.name)
def test_every_panel_points_at_a_datasource_that_is_provisioned(path):
    """
    The failure this prevents is silent: Grafana provisions both files happily,
    logs no error, and renders "No data" on every panel — indistinguishable from
    a shop with no traffic.
    """
    dashboard = json.loads(path.read_text())
    referenced = _panel_datasource_uids(dashboard)
    declared = _datasource_uids()

    missing = referenced - declared
    assert not missing, (
        f"{path.name} references datasource uid(s) {sorted(missing)} "
        f"which no provisioning file declares (declared: {sorted(declared)})"
    )


@pytest.mark.parametrize("path", _dashboard_files(), ids=lambda p: p.name)
def test_dashboard_is_valid_json_with_a_stable_uid(path):
    dashboard = json.loads(path.read_text())

    # The uid is what the URL and any bookmark depend on.
    assert dashboard.get("uid"), f"{path.name} has no dashboard uid"
    assert dashboard.get("title"), f"{path.name} has no title"
    assert dashboard.get("panels"), f"{path.name} has no panels"


@pytest.mark.parametrize("path", _dashboard_files(), ids=lambda p: p.name)
def test_every_panel_has_a_query(path):
    """A panel with no target is a box that can only ever say "No data"."""
    dashboard = json.loads(path.read_text())

    for panel in dashboard["panels"]:
        if panel.get("type") == "row":
            continue
        targets = panel.get("targets") or []
        assert targets, f"{panel.get('title')} has no query"
        assert targets[0].get("expr"), f"{panel.get('title')} has an empty query"
