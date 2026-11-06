#!/usr/bin/env python3
"""수강생 배포본 생성 (강사용) — 정답 · 강사 자료를 뺀 새 저장소를 만든다. git 기록은 넘기지 않는다

  python3 _instructor/make_release.py <빈 폴더>
"""
import io, shutil, subprocess, sys, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = ("_instructor/", "dev/defects/", "tools/defect_score.py", "reviews/")
FORBIDDEN = ("signal-key", "answers.json", "answers.hash", "unseen/cfo")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    if out.exists() and any(out.iterdir()):
        print(f"비어 있지 않은 폴더입니다: {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    data = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        members = [m for m in t.getmembers() if not (m.name + "/").startswith(EXCLUDE)]
        t.extractall(out, members=members, filter="data")
    readme = out / "README.md"
    readme.write_text("\n".join(l for l in readme.read_text(encoding="utf-8").splitlines() if "_instructor" not in l) + "\n", encoding="utf-8")
    left = [str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and any(f in str(p) for f in FORBIDDEN)]
    if left or (out / "_instructor").exists():
        shutil.rmtree(out)
        print(f"배포본에 강사 자료가 남아 중단했습니다: {left}", file=sys.stderr)
        return 1
    r = subprocess.run([sys.executable, "tools/test_tools.py"], cwd=out, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-800:], file=sys.stderr)
        return 1
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=mi-skillkit", "-c", "user.email=mi@local", "commit", "-qm", "수강생 배포본"]):
        subprocess.run(["git", *cmd], cwd=out, check=True)
    print(f"완료: {out} · 파일 {sum(1 for p in out.rglob('*') if p.is_file() and '.git/' not in str(p))}개 · 테스트 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
