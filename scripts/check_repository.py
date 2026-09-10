#!/usr/bin/env python3
"""외부 의존성 없이 한국어 스킬 패키지의 정적 일관성을 검사한다."""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "xiaohei-illustrations"
KOREAN = re.compile(r"[\uac00-\ud7a3]")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
SVG = "{http://www.w3.org/2000/svg}"
EXAMPLES = (
    "01-information-overload", "02-small-validation", "03-content-reuse",
    "04-context-handoff", "05-evidence", "06-feedback-loop", "07-priority",
    "08-knowledge-compounding",
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> None:
    references = ("style-dna", "xiaohei-ip", "composition-patterns", "prompt-template", "qa-checklist")
    required = [ROOT / p for p in ("README.md", "AGENTS.md", "NOTICE.md", "LICENSE", "examples/prompts.md")]
    required += [SKILL / p for p in ("SKILL.md", "LICENSE", "NOTICE.md", "agents/openai.yaml", "assets/examples/README.md")]
    required += [SKILL / "references" / (name + ".md") for name in references]
    check(all(p.is_file() for p in required), "필수 문서 또는 설치 파일이 없습니다.")
    packages = sorted(p.parent.relative_to(ROOT).as_posix() for p in ROOT.glob("*/SKILL.md"))
    check(packages == ["xiaohei-illustrations"], "설치 폴더가 중복되거나 이름이 다릅니다.")
    check(not (ROOT / "examples/images").exists(), "예제 이미지는 설치 폴더에서만 관리하세요.")
    check((ROOT / "LICENSE").read_bytes() == (SKILL / "LICENSE").read_bytes(), "동봉 라이선스가 원본과 다릅니다.")
    check((ROOT / "NOTICE.md").read_bytes() == (SKILL / "NOTICE.md").read_bytes(), "동봉 안내문이 다릅니다.")

    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"---\n(.*?)\n---\n", skill_text, re.S)
    check(front is not None, "스킬 머리말이 없습니다.")
    fields = dict(line.split(": ", 1) for line in front.group(1).splitlines())
    check(fields.get("name") == SKILL.name, "스킬 이름과 설치 폴더가 다릅니다.")
    check(bool(KOREAN.search(fields.get("description", ""))), "스킬 설명은 한국어여야 합니다.")
    for target in re.findall(r"`((?:references/|assets/examples/)[^`]+\.md)`", skill_text):
        check((SKILL / target).is_file(), f"없는 스킬 참조: {target}")
    agent_text = (SKILL / "agents/openai.yaml").read_text(encoding="utf-8")
    for field in ("display_name", "short_description", "default_prompt"):
        match = re.search(rf'^  {field}: "(.+)"$', agent_text, re.M)
        check(match is not None and bool(KOREAN.search(match.group(1))), f"한국어 에이전트 필드 오류: {field}")
    check("$xiaohei-illustrations" in agent_text, "기본 프롬프트의 실행 이름이 다릅니다.")
    check("  allow_implicit_invocation: true" in agent_text, "호출 정책을 확인하세요.")

    assets = SKILL / "assets/examples"
    images = sorted(assets.glob("*.svg"))
    check([p.stem for p in images] == list(EXAMPLES), "한국어 구성 예제 8개를 확인하세요.")
    check({p.name for p in assets.iterdir()} == {"README.md", *(name + ".svg" for name in EXAMPLES)}, "예제 폴더에 불필요한 파일이 있습니다.")
    allowed = {"svg", "title", "desc", "rect", "defs", "g", "path", "circle", "use", "text"}
    catalog = (assets / "README.md").read_text(encoding="utf-8")
    for image in images:
        tree = ET.parse(image).getroot()
        check(tree.tag == SVG + "svg" and tree.get("viewBox") == "0 0 1280 720", f"SVG 비율 오류: {image.name}")
        check(tree.get("{http://www.w3.org/XML/1998/namespace}lang") == "ko", f"SVG 언어 오류: {image.name}")
        check(tree.find(SVG + "title") is not None and tree.find(SVG + "desc") is not None, f"SVG 접근성 설명 누락: {image.name}")
        labels = ["".join(node.itertext()) for node in tree.iter(SVG + "text")]
        check(3 <= len(labels) <= 8 and all(KOREAN.search(label) for label in labels), f"한글 주석 오류: {image.name}")
        check(all(label in catalog for label in labels), f"예제 목록과 한글 표기가 다릅니다: {image.name}")
        for node in tree.iter():
            check(node.tag.startswith(SVG) and node.tag[len(SVG):] in allowed, f"허용하지 않은 SVG 요소: {image.name}")
            for key, value in node.attrib.items():
                check(not key.lower().startswith("on"), f"SVG 이벤트 실행 금지: {image.name}")
                if key.endswith("href"):
                    check(value.startswith("#"), f"SVG 외부 참조 금지: {image.name}")

    checked = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        check(not re.search(r"(?:qr|wechat)", path.name, re.I), f"불필요한 자산: {path.name}")
        if path.suffix not in {".md", ".yaml", ".svg"}:
            continue
        text = path.read_text(encoding="utf-8")
        check(not CJK.search(text), f"번역되지 않은 한자 표기: {path.relative_to(ROOT)}")
        check(bool(KOREAN.search(text)), f"한국어 설명 누락: {path.relative_to(ROOT)}")
        if path.suffix == ".md":
            # 코드 예시 안의 대괄호는 문서 링크로 취급하지 않는다.
            prose = re.sub(r"```.*?```", "", text, flags=re.S)
            for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", prose):
                if target.startswith(("https://", "http://", "#")):
                    continue
                local = (path.parent / target.split("#", 1)[0]).resolve()
                check(local.is_relative_to(ROOT) and local.exists(), f"끊어진 문서 링크: {path.name}: {target}")
        checked += 1
    print(f"통과: 한국어 문서·설정·예제 {checked}개, SVG {len(images)}개, 스킬 이름·참조·라이선스·문서 링크")


if __name__ == "__main__":
    try:
        validate()
    except (ValueError, OSError, ET.ParseError) as error:
        print(f"실패: {error}", file=sys.stderr)
        sys.exit(1)
