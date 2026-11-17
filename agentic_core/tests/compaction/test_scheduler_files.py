"""The scheduler wrappers must start the job at the time in config.yaml (RP-18, section 4).

The wrappers hold no logic, so we only check that they agree with the
settings and call the right Python entry point.
"""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from agentic_core.compaction.config import load_config

SCHEDULER = Path(__file__).resolve().parents[3] / "scripts" / "scheduler"
NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
ENTRY = "agentic_core.compaction.run"


def test_cron_line_matches_run_time_and_time_zone():
    config = load_config()
    hour, minute = (int(x) for x in config.run_time.split(":"))
    lines = [
        line.strip()
        for line in (SCHEDULER / "compaction.cron").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert f"CRON_TZ={config.time_zone}" in lines
    (job,) = [line for line in lines if not line.startswith("CRON_TZ")]
    assert re.match(rf"^{minute} {hour} \* \* \* \S+/run_compaction\.sh \S+$", job)


def test_task_scheduler_xml_matches_run_time_and_is_safe():
    config = load_config()
    text = (SCHEDULER / "compaction_task.xml").read_text(encoding="utf-8")
    root = ET.fromstring(text.split("?>", 1)[1])  # skip the UTF-16 declaration line
    start = root.find("t:Triggers/t:CalendarTrigger/t:StartBoundary", NS).text
    assert start.endswith(f"T{config.run_time}:00")
    assert root.find("t:Triggers/t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval", NS).text == "1"
    settings = root.find("t:Settings", NS)
    assert settings.find("t:StartWhenAvailable", NS).text == "true"  # catch up after sleep
    assert settings.find("t:MultipleInstancesPolicy", NS).text == "IgnoreNew"  # never two at once
    assert root.find("t:Principals/t:Principal/t:RunLevel", NS).text == "LeastPrivilege"
    arguments = root.find("t:Actions/t:Exec/t:Arguments", NS).text
    assert "run_compaction.ps1" in arguments and "-Vault" in arguments


def test_both_wrappers_call_the_same_entry_point_and_hold_no_logic():
    for name in ("run_compaction.ps1", "run_compaction.sh"):
        text = (SCHEDULER / name).read_text(encoding="utf-8")
        assert f"-m {ENTRY} --vault" in text
        assert ".venv" in text
        assert "--log-file" in text
