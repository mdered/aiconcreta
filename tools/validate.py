#!/usr/bin/env python3
"""Checks drafts against the post format (tools/postspec.py).

    python3 tools/validate.py                      # every draft in drafts/
    python3 tools/validate.py drafts/<id>/post.json
Exit code 1 if any draft has a problem.
"""
import glob, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import postspec  # noqa: E402

paths = sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, "drafts", "*", "post.json")))
bad = 0
for p in paths:
    try:
        post = json.load(open(p, encoding="utf-8"))
        problems = postspec.check(post, os.path.basename(os.path.dirname(os.path.abspath(p))))
    except ValueError as e:
        problems = [f"not valid JSON: {e}"]
    if problems:
        bad += 1
        print(f"✗ {os.path.relpath(p, ROOT)}\n  " + "\n  ".join(problems))
    else:
        print(f"✓ {os.path.relpath(p, ROOT)} ({len(postspec.full_caption(post))} caption characters)")
print(f"{len(paths)} checked, {bad} with problems")
sys.exit(1 if bad else 0)
