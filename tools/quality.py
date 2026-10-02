"""Normalize identities and validate the published question bank."""
import collections
import datetime
import hashlib
import json
import pathlib
import re


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def normalized(s):
    return re.sub(r"\s+", "", s)


def normalize(root):
    index = read(root / "data/index.json")
    fixes = read(pathlib.Path(__file__).with_name("answer-pages.json"))
    rows, files, groups = [], {}, collections.defaultdict(list)
    for meta in index["chapters"] + index["exams"]:
        name = f"ch{meta['no']}" if "no" in meta else meta["id"]
        data = read(root / "data" / f"{name}.json")
        files[name] = data
        for q in data["questions"]:
            if not q["q"].strip():
                parts = re.split(r"【问题】", q.get("ctx", ""), maxsplit=1)
                if len(parts) == 2:
                    q["ctx"], q["q"] = (part.strip() for part in parts)
                else:
                    q["q"], q["ctx"] = q.get("ctx", "").strip(), ""
            if q["id"] in fixes:
                fix = fixes[q["id"]]
                q["pages"] = [f"pages/{fix['fileId']}/p{n}.jpg" for n in fix["questionPages"]]
                q["answerPages"] = [f"pages/{fix['fileId']}/p{n}.jpg" for n in fix["answerPages"]]
                q["a"] = "本题参考答案为公式图片，请查看下方原始答案页。"
            rows.append((name, q))
            groups[(normalized(q.get("ctx", "")), normalized(q["q"]))].append((name, q))
    aliases, duplicates = {}, []
    for group in groups.values():
        # Merge only identical prompts AND answers. Different answers remain distinct.
        by_answer = collections.defaultdict(list)
        for name, q in group:
            by_answer[(normalized(q["a"]), tuple(q.get("answerPages", [])))].append((name, q))
        for same in by_answer.values():
            canonical = min(q["id"] for _, q in same)
            chapters = sorted({files[n]["no"] for n, _ in same if "no" in files[n]})
            for _, q in same:
                q["canonicalId"] = canonical
                q["chapters"] = chapters
                if q["id"] != canonical:
                    aliases[q["id"]] = canonical
        if len(group) > 1:
            duplicates.append({"ids": [q["id"] for _, q in group],
                               "merged": len(by_answer) == 1,
                               "question": group[0][1]["q"][:180]})
    for meta in index["chapters"] + index["exams"]:
        name = f"ch{meta['no']}" if "no" in meta else meta["id"]
        data = files[name]
        meta["questionIds"] = list(dict.fromkeys(q["canonicalId"] for q in data["questions"]))
        meta["n"] = len(data["questions"])
        if "no" in meta:
            meta["notes"] = len(data.get("notes", []))
            meta["srcs"] = dict(collections.Counter(q["src"] for q in data["questions"]))
        else:
            meta.setdefault("kind", "mock")
        write(root / "data" / f"{name}.json", data)
    index["aliases"] = aliases
    index["uniqueQuestions"] = len({q["canonicalId"] for _, q in rows})
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update((root / "data" / f"{name}.json").read_bytes())
    index["version"] = digest.hexdigest()[:16]
    index["generated"] = datetime.date.today().isoformat()
    write(root / "data/index.json", index)
    return duplicates


def validate(root):
    index = read(root / "data/index.json")
    ids, canonical, counts, prompts = set(), set(), collections.Counter(), {}
    for meta in index["chapters"] + index["exams"]:
        name = f"ch{meta['no']}" if "no" in meta else meta["id"]
        data = read(root / "data" / f"{name}.json")
        assert len(data["questions"]) == meta["n"], name
        assert meta["questionIds"] == list(dict.fromkeys(q["canonicalId"] for q in data["questions"])), name
        if "no" in meta:
            assert meta["notes"] == len(data.get("notes", [])), name
            assert meta["srcs"] == dict(collections.Counter(q["src"] for q in data["questions"])), name
        for q in data["questions"]:
            assert q["id"] not in ids, f"Duplicate ID: {q['id']}"
            ids.add(q["id"])
            for field in ("id", "q", "a", "src", "type", "canonicalId"):
                assert isinstance(q.get(field), str) and q[field].strip(), (q["id"], field)
            for url in q.get("pages", []) + q.get("answerPages", []):
                path = (root / url).resolve()
                assert path.is_relative_to(root.resolve()) and path.is_file(), url
            assert not re.search("无法提取|未找到|未提供", q["a"]) or q.get("answerPages"), q["id"]
            canonical.add(q["canonicalId"])
            signature = (normalized(q.get("ctx", "")), normalized(q["q"]), normalized(q["a"]), tuple(q.get("answerPages", [])))
            assert q["canonicalId"] not in prompts or prompts[q["canonicalId"]] == signature, q["id"]
            prompts[q["canonicalId"]] = signature
            counts["questions"] += 1
    assert canonical <= ids
    assert index["uniqueQuestions"] == len(canonical)
    assert all(k in ids and v in canonical for k, v in index["aliases"].items())
    counts["uniqueQuestions"] = len(canonical)
    return dict(counts)


if __name__ == "__main__":
    print(validate(pathlib.Path(__file__).resolve().parents[1]))
