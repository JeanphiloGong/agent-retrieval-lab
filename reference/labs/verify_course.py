"""Inventory the supplied course materials, independent of learner progress."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


TOPICS = {
    "01-evaluation": "evaluation",
    "02-code-search": "code_search",
    "03-document-evidence": "documents",
    "04-hybrid-retrieval": "hybrid",
    "05-document-navigation": "navigation",
    "06-live-data": "live_data",
    "07-agent-loop": "agent",
    "08-access-control": "access",
    "09-index-operations": "operations",
}


def verify(root: Path) -> dict[str, int]:
    tutorials = root / "tutorials"
    errors: list[str] = []
    topic_count = 0
    version_count = 0
    tutorial_count = 0
    for topic, package in TOPICS.items():
        topic_dir = tutorials / topic
        if not (topic_dir / "README.md").exists():
            errors.append(f"missing {topic}/README.md")
            continue
        topic_count += 1
        versions = sorted(topic_dir.glob("v*/plan.md"))
        for plan in versions:
            version_count += 1
            body = plan.read_text(encoding="utf-8")
            if not re.search(r"参考状态：verified", body):
                errors.append(f"unverified reference plan: {plan.relative_to(root)}")
            if not plan.with_name("tutorial.md").exists():
                errors.append(f"missing tutorial: {plan.parent.relative_to(root)}/tutorial.md")
            else:
                tutorial_count += 1
        if not (root / "reference" / "labs" / package).exists():
            errors.append(f"missing reference package: reference/labs/{package}")
        if not (root / "tests").exists():
            errors.append("missing tests directory")
    if topic_count != 9 or version_count != 37 or tutorial_count != 37:
        errors.append(f"expected 9 topics, 37 plans and 37 tutorials; got {topic_count}, {version_count}, {tutorial_count}")
    if errors:
        raise SystemExit("\n".join(errors))
    return {"topics": topic_count, "versions": version_count, "tutorials": tutorial_count}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, default=Path("."), nargs="?")
    args = parser.parse_args()
    result = verify(args.root.resolve())
    print("course structure verified: " + ", ".join(f"{key}={value}" for key, value in result.items()))
