"""Exercise inventory generator.

Reads topic-map.json (colocated with this script) and enumerates every exercise
across the finished/, starter/, and instructions/ trees. Emits a JSON inventory
by default, or a Markdown table with --markdown.

Every path returned is repo-root-relative so downstream skills can use them
without knowing where this script lives.
"""
import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
TOPIC_MAP_PATH = SCRIPT_DIR / "topic-map.json"


def load_topic_map() -> dict:
    with TOPIC_MAP_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_inventory(topic_map: dict) -> list[dict]:
    exercises: list[dict] = []
    for topic_slug, topic in topic_map["topics"].items():
        instructions_dir = topic["instructions_dir"]
        starter_topic = topic.get("starter_topic", topic_slug)
        for exercise_slug, exercise in topic["exercises"].items():
            starter_slug = exercise.get("starter_slug")
            finished_dir = f"finished/{topic_slug}/{exercise_slug}"
            starter_dir = (
                f"starter/{starter_topic}/{starter_slug}"
                if starter_slug else None
            )
            instructions_file = (
                f"instructions/{instructions_dir}/{exercise['instructions_file']}"
            )
            exercises.append({
                "id": f"{topic_slug}/{exercise_slug}",
                "topic": topic_slug,
                "exercise": exercise_slug,
                "finished_dir": finished_dir,
                "starter_dir": starter_dir,
                "instructions_file": instructions_file,
            })
    return exercises


def check_existence(exercises: list[dict]) -> list[dict]:
    checked = []
    for exercise in exercises:
        entry = dict(exercise)
        entry["finished_exists"] = (REPO_ROOT / exercise["finished_dir"]).is_dir()
        entry["starter_exists"] = (
            (REPO_ROOT / exercise["starter_dir"]).is_dir()
            if exercise["starter_dir"] else False
        )
        entry["instructions_exists"] = (
            REPO_ROOT / exercise["instructions_file"]
        ).is_file()
        checked.append(entry)
    return checked


def emit_json(exercises: list[dict]) -> None:
    payload = {
        "repo_root": str(REPO_ROOT),
        "count": len(exercises),
        "exercises": exercises,
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def emit_markdown(exercises: list[dict]) -> None:
    print("| id | finished | starter | instructions | missing |")
    print("|---|---|---|---|---|")
    for exercise in exercises:
        missing = []
        if not exercise.get("finished_exists", True):
            missing.append("finished")
        if exercise["starter_dir"] and not exercise.get("starter_exists", True):
            missing.append("starter")
        if not exercise.get("instructions_exists", True):
            missing.append("instructions")
        missing_display = ", ".join(missing) if missing else "-"
        starter_display = exercise["starter_dir"] or "(none)"
        print(
            f"| {exercise['id']} "
            f"| {exercise['finished_dir']} "
            f"| {starter_display} "
            f"| {exercise['instructions_file']} "
            f"| {missing_display} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Emit a printable Markdown table instead of JSON.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Include existence checks for every path.",
    )
    args = parser.parse_args()

    topic_map = load_topic_map()
    exercises = build_inventory(topic_map)
    if args.check or args.markdown:
        exercises = check_existence(exercises)

    if args.markdown:
        emit_markdown(exercises)
    else:
        emit_json(exercises)
    return 0


if __name__ == "__main__":
    sys.exit(main())
