#!/usr/bin/env python3
"""export_skill.py — 깎은 작업 지침을 어디든 가져갈 수 있는 스킬 폴더로 내보낸다

  python3 tools/export_skill.py <내보낼 폴더> [--name mi-brief]
"""
import argparse, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--name", default="mi-brief")
a = ap.parse_args()
stub = (ROOT / ".claude/skills" / a.name / "SKILL.md").read_text(encoding="utf-8")
head = re.match(r"---\n.*?\n---\n", stub, re.S).group(0)
body = (ROOT / "playbook" / f"{a.name}.md").read_text(encoding="utf-8")
dest = Path(a.out) / a.name
dest.mkdir(parents=True, exist_ok=True)
(dest / "SKILL.md").write_text(head + "\n" + body, encoding="utf-8")
print(dest / "SKILL.md")
