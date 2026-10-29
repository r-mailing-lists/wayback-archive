#!/usr/bin/env python3
"""Fetch a list's monthly pipermail files from the Wayback Machine.

    tools/wayback.py fetch <list>    download the months not yet in <list>/wayback.json
    tools/wayback.py check <list>    count whole addresses in message text (counts only)

<list>/config.json names the list's original archive in source_url, for
example https://lists.gking.harvard.edu/pipermail/amelia/. The Wayback
Machine's index (the CDX API) is asked for every capture under it, and for
each month the newest capture of <Year>-<Month>.txt.gz is taken (or of the
plain .txt when no .gz was saved). Each file is downloaded once, unchanged
(the id_ form of the address), unzipped, and written to
<list>/raw/<Year>-<Month>.mbox. <list>/wayback.json records which capture
each month came from, so a later run fetches only months that were missing.
One request at a time, with a pause between them.
"""

import gzip
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "r-mailing-lists archive recovery (github.com/r-mailing-lists/wayback-archive)"
PAUSE = 5
MONTH_FILE = re.compile(r"(\d{4}-[A-Z][a-z]+)\.txt(\.gz)?")
START = re.compile(r"(?m)^(?=From \S+(?: at \S+)?  \w{3} \w{3} [ \d]\d \d\d:\d\d:\d\d \d{4}$)")
ADDRESS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            return urllib.request.urlopen(request, timeout=300).read()
        except OSError as e:
            print(f"  retrying after {type(e).__name__}", flush=True)
            time.sleep(30 * (attempt + 1))
    raise SystemExit(f"could not fetch {url}")


def newest_captures(rows):
    """{month: (timestamp, url)} from CDX rows [original, timestamp, statuscode]:
    the newest 200 capture of each month's file, a .txt.gz before a .txt."""
    best = {}
    for original, timestamp, status in rows:
        match = MONTH_FILE.fullmatch(original.rsplit("/", 1)[-1])
        if status != "200" or not match:
            continue
        rank = (match.group(2) is not None, timestamp)
        month = match.group(1)
        if month not in best or rank > best[month][0]:
            best[month] = (rank, timestamp, original)
    return {month: (ts, url) for month, (_, ts, url) in best.items()}


def fetch(list_dir):
    config = json.loads((list_dir / "config.json").read_text())
    prefix = re.sub(r"^https?://", "", config["source_url"])
    query = urllib.parse.urlencode({"url": prefix + "*", "output": "json",
                                    "fl": "original,timestamp,statuscode", "limit": "50000"})
    rows = json.loads(get("https://web.archive.org/cdx/search/cdx?" + query))[1:]
    record_path = list_dir / "wayback.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    (list_dir / "raw").mkdir(exist_ok=True)
    for month, (timestamp, url) in sorted(newest_captures(rows).items()):
        if month in record:
            continue
        data = get(f"https://web.archive.org/web/{timestamp}id_/{url}")
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        if data and not data.startswith(b"From "):
            print(f"{month}: not an mbox, passed over", flush=True)
            continue
        (list_dir / "raw" / f"{month}.mbox").write_bytes(data)
        record[month] = {"timestamp": timestamp, "url": url, "sha256": hashlib.sha256(data).hexdigest()}
        record_path.write_text(json.dumps(dict(sorted(record.items())), indent=1) + "\n")
        print(f"{month}: {len(START.findall(data.decode('latin-1')))} messages, captured {timestamp[:8]}", flush=True)
        time.sleep(PAUSE)


def check(list_dir):
    """Count whole addresses in message text, leaving out the headers (whose
    Message-IDs look like addresses). Prints where, never what."""
    total = 0
    for path in sorted((list_dir / "raw").glob("*.mbox")):
        for message in START.split(path.read_text(encoding="latin-1")):
            if not message.startswith("From "):
                continue
            headers, _, body = message.partition("\n\n")
            if re.search(r"(?m)^From: .*\S@\S", headers):
                print(f"{path.name}: a whole address in a From: line")
            total += len(ADDRESS.findall(body))
    print(f"{list_dir.name}: {total} whole addresses in message text")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("fetch", "check"):
        raise SystemExit(__doc__)
    list_dir = Path(__file__).resolve().parent.parent / sys.argv[2]
    if not (list_dir / "config.json").exists():
        raise SystemExit(f"No such list: {sys.argv[2]}")
    (fetch if sys.argv[1] == "fetch" else check)(list_dir)


if __name__ == "__main__":
    main()
