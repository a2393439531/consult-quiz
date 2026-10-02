"""Stage, validate and publish a complete local question bank."""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from quality import normalize, validate, read, write

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reparse", action="store_true", help="Regenerate from configured text/PDF sources")
    parser.add_argument("--config", type=pathlib.Path, default=ROOT / "tools/config.local.json")
    args = parser.parse_args()
    config = read(args.config) if args.config.exists() else {}
    # Create sibling staging on the same filesystem, so directory promotion is a rename.
    with tempfile.TemporaryDirectory(prefix="quiz-build-", dir=ROOT.parent) as tmp:
        stage = pathlib.Path(tmp)
        shutil.copytree(ROOT / "data", stage / "data")
        shutil.copytree(ROOT / "pages", stage / "pages")
        if args.reparse:
            env = dict(os.environ, PYTHONUTF8="1", QUIZ_DATA_DIR=str(stage / "data"), QUIZ_OUTPUT_DIR=str(stage))
            for key, variable in [("textDir", "QUIZ_TEXT_DIR"), ("text2Dir", "QUIZ_TEXT2_DIR"), ("pdfDir", "QUIZ_PDF_DIR")]:
                path = pathlib.Path(config[key]).resolve()
                if not path.is_dir():
                    raise ValueError(f"Missing source directory: {path}")
                env[variable] = str(path)
            for script in ["parse.py", "parse3.py", "pagemaps.py"]:
                result = subprocess.run([sys.executable, str(ROOT / "tools" / script)], env=env,
                                        capture_output=True, text=True, encoding="utf-8")
                if result.returncode:
                    raise RuntimeError(f"{script} failed:\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")
                print(f"{script}: complete")
            import pymupdf
            for fix in read(ROOT / "tools/answer-pages.json").values():
                with pymupdf.open(pathlib.Path(config["pdfDir"]) / fix["pdf"]) as doc:
                    folder = stage / "pages" / fix["fileId"]
                    folder.mkdir(parents=True, exist_ok=True)
                    for n in set(fix["questionPages"] + fix["answerPages"]):
                        output = folder / f"p{n}.jpg"
                        if n in fix["answerPages"] or not output.exists():
                            doc[n - 1].get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6)).save(output, jpg_quality=75)
        duplicates = normalize(stage)
        result = validate(stage)
        before_ids = {q["id"] for path in (ROOT / "data").glob("*.json") for q in read(path).get("questions", [])}
        after_ids = {q["id"] for path in (stage / "data").glob("*.json") for q in read(path).get("questions", [])}
        if before_ids - after_ids:
            raise ValueError(f"Build lost existing questions: {sorted(before_ids - after_ids)[:20]}")
        # Publish with rollback. A failed parse or gate never reaches this step.
        promoted, backups = [], []
        try:
            for name in ["pages", "data"]:
                backup = stage / f"old-{name}"
                (ROOT / name).rename(backup)
                backups.append((name, backup))
                (stage / name).rename(ROOT / name)
                promoted.append(name)
        except Exception:
            for name in reversed(promoted):
                (ROOT / name).rename(stage / f"failed-{name}")
            for name, backup in reversed(backups):
                backup.rename(ROOT / name)
            raise
        reports = ROOT / "reports"
        reports.mkdir(exist_ok=True)
        write(reports / "duplicates.json", duplicates)
        write(reports / "validation.json", result)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
