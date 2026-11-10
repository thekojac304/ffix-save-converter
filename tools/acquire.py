"""Download public save fixtures byte-for-byte and record provenance.

Usage: python -I tools/acquire.py <sources.json> <dest_dir> <provenance.jsonl>

sources.json is a list of {"url", "filename", "source_page", "description", ...}.
Files are written once and never overwritten; existing files are re-hashed only.
Nothing downloaded is ever executed or extracted here.
"""
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.request

MAX_BYTES = 50 * 1024 * 1024
UA = "Mozilla/5.0 (FFIX-Save-Converter research; fixture acquisition)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("download exceeds size cap")
        return resp.status, resp.headers.get("Content-Type", ""), data


def main(sources_path, dest_dir, prov_path):
    with open(sources_path, encoding="utf-8") as f:
        sources = json.load(f)
    os.makedirs(dest_dir, exist_ok=True)
    done = set()
    if os.path.exists(prov_path):
        with open(prov_path, encoding="utf-8") as f:
            done = {json.loads(line)["url"] for line in f if line.strip()}
    with open(prov_path, "a", encoding="utf-8") as prov:
        for src in sources:
            if src["url"] in done:
                continue
            name = os.path.basename(src["filename"])
            path = os.path.join(dest_dir, name)
            rec = dict(src)
            rec["retrieved_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            try:
                if os.path.exists(path):
                    raise FileExistsError("refusing to overwrite existing original")
                status, ctype, data = fetch(src["url"])
                with open(path, "xb") as out:
                    out.write(data)
                rec.update(status=status, content_type=ctype, size=len(data),
                           sha256=hashlib.sha256(data).hexdigest(), stored_as=name, ok=True)
            except Exception as e:  # record failures honestly
                rec.update(ok=False, error=f"{type(e).__name__}: {e}")
            prov.write(json.dumps(rec) + "\n")
            prov.flush()
            print(("OK  " if rec["ok"] else "ERR ") + name, rec.get("size", rec.get("error")))
            time.sleep(1.0)  # be polite to small community hosts


if __name__ == "__main__":
    main(*sys.argv[1:4])
