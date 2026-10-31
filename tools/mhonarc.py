#!/usr/bin/env python3
"""Rebuild a list whose MHonArc archive the Wayback Machine saved.

    tools/mhonarc.py fetch <list>         read every saved page into <list>/.cache/
    tools/mhonarc.py build <list>         write <list>/raw/ from the pages in <list>/.cache/
    tools/mhonarc.py add <list> <mbox>    add the messages of another copy that raw/ lacks

MHonArc filed a list as a page per message, by month, with no mbox to
download. <list>/config.json names the archive in source_url, for example
http://www.biostat.wustl.edu/archives/html/s-news/. fetch asks the Wayback
Machine's index (the CDX API) for every saved message page under it and for
the newest copy of each month's index, and reads each once, unchanged (the
id_ form of the address), one request at a time with a pause between them.
The pages hold plain addresses, so they stay in <list>/.cache/, which git
ignores; <list>/wayback.json records which capture each page came from, and
a later run reads only the pages not yet in the cache.

build writes each month as pipermail's text archives would: From, Date,
Subject, In-Reply-To, References and Message-ID only, the sender and every
address in a subject or in the text written "user at domain", an attachment
named after Mailman's "next part" line. The Date is written in RFC 2822's form
whatever form the sender's mailer gave it, as rmail-parser passes over a
message whose date it cannot read. It prints, for each month, how many
messages its index names that the Wayback Machine never saved.

add takes another copy of the list as an mbox (Gmane's, say) and writes the
messages whose Message-ID raw/ does not have to raw/from-<name>.mbox.

config.json may name the last month to keep in until (YYYY-MM): build and add
then leave out every message sent after it, by the date in UTC the site files
it under. S-news has one, as its archive was public only until then.
"""

import html
import json
import re
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.header import Header, decode_header, make_header
from email.utils import format_datetime, getaddresses, parsedate_to_datetime
from pathlib import Path

UA = "r-mailing-lists archive recovery (github.com/r-mailing-lists/wayback-archive)"
PAUSE = 5  # seconds between requests, one at a time: the Wayback Machine refuses a reader who asks faster
PAGE = re.compile(r"/(\d{4}-\d{2})/(msg\d+|index|threads)\.html$")
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------

def get(url):
    """The body at url; None for an answer that is not a page (404, 403).
    Waits and tries again on a refusal or a fault, for minutes and then up
    to an hour, as a reader it has refused is shut out for a while, and gives
    up (the run stops, and the next one carries on) when it keeps refusing."""
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    for wait in (300, 900, 1800, 3600, 3600):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None
            print(f"  HTTP {e.code}, waiting {wait} s", flush=True)
        except OSError as e:
            print(f"  {type(e).__name__}, waiting {wait} s", flush=True)
        time.sleep(wait)
    raise SystemExit(f"stopped: the Wayback Machine kept refusing {url}")


def cdx(prefix, **params):
    query = urllib.parse.urlencode({"url": prefix + "*", "output": "json",
                                    "fl": "original,timestamp", "filter": "statuscode:200",
                                    "limit": "200000", **params}, doseq=True)
    body = get("https://web.archive.org/cdx/search/cdx?" + query)
    return json.loads(body)[1:] if body else []


def captures(prefix):
    """{"YYYY-MM/name.html": (timestamp, original)}: a capture of every saved
    message page, and the newest of each month's index (an older one may
    have been saved before the month ended)."""
    pages = {}
    for original, timestamp in cdx(prefix, collapse="urlkey"):
        m = PAGE.search(original)
        if m and m.group(2).startswith("msg"):
            pages[f"{m.group(1)}/{m.group(2)}.html"] = (timestamp, original)
    for original, timestamp in cdx(prefix, filter=["statuscode:200", r"original:.*/(index|threads)\.html"]):
        m = PAGE.search(original)
        key = m and f"{m.group(1)}/{m.group(2)}.html"
        if key and (key not in pages or timestamp > pages[key][0]):
            pages[key] = (timestamp, original)
    return pages


def is_page(name, body):
    if name.startswith("msg"):
        return b"<!--X-Head-End-->" in body and b"<!--X-Body-of-Message-->" in body
    return b"MHonArc" in body


def fetch(list_dir):
    config = json.loads((list_dir / "config.json").read_text())
    prefix = re.sub(r"^https?://", "", config["source_url"])
    record_path = list_dir / "wayback.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {}
    cache = list_dir / ".cache"
    wanted = sorted(captures(prefix).items())
    # A page a cut run stored after its last write of the record is in the
    # cache and not yet in the record.
    for key, (timestamp, _) in wanted:
        if key not in record and (cache / key).exists():
            record[key] = timestamp
    todo = [(k, v) for k, v in wanted if not (cache / k).exists()]
    print(f"{len(wanted)} pages saved, {len(todo)} not yet read", flush=True)
    passed = 0
    for done, (key, (timestamp, original)) in enumerate(todo, 1):
        body = get(f"https://web.archive.org/web/{timestamp}id_/{original}")
        if body is None or not is_page(key.rsplit("/", 1)[1], body):
            passed += 1
            print(f"  {key}: not an archive page, passed over", flush=True)
        else:
            (cache / key).parent.mkdir(parents=True, exist_ok=True)
            (cache / key).write_bytes(body)
            record[key] = timestamp
        if done % 100 == 0 or done == len(todo):
            record_path.write_text(json.dumps(dict(sorted(record.items())), indent=0) + "\n")
            print(f"{done} of {len(todo)} read ({passed} passed over)", flush=True)
        time.sleep(PAUSE)


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def page_text(path):
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def comments(page):
    """The X- comments MHonArc puts above a page's head, as (key, value)."""
    head = page[:page.find("<!--X-Head-End-->")]
    return [(k, html.unescape(v)) for k, v in re.findall(r"<!--X-([\w-]+): (.*?) -->", head)]


def section(page, name):
    start = page.find(f"<!--X-{name}-->")
    end = page.find(f"<!--X-{name}-End-->")
    return page[start + len(name) + 9:end] if 0 <= start < end else ""


def strip_tags(markup):
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def html_to_text(markup):
    markup = re.sub(r"(?is)<(script|style).*?</\1>", "", markup)
    markup = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>|<hr\s*/?>", "\n", markup)
    return strip_tags(markup)


def fields(page):
    """The headers MHonArc lists above a message, by lower-case name: rows
    of a table (MHonArc 2.6) or items of a list (later versions)."""
    head = section(page, "Head-of-Message")
    found = {}
    rows = re.findall(r"(?s)<strong>([^<]+)</strong>:\s*</th>\s*<td[^>]*>(.*?)</td>", head)
    rows += re.findall(r"(?s)<li><em>([^<]+)</em>: (.*?)</li>", head)
    for key, value in rows:
        found.setdefault(key.strip().lower(), " ".join(strip_tags(value).split()))
    return found


def ids(value):
    return re.findall(r"<([^<>\s]+)>", value)


# MHonArc writes the raw From header in X-From-R13 with "@A-Z[" and a-z
# rotated by half (its mrot13).
_PLAIN = "@" + string.ascii_uppercase + "[" + string.ascii_lowercase
_ROTATED = _PLAIN[14:28] + _PLAIN[:14] + _PLAIN[41:] + _PLAIN[28:41]
UNROT13 = str.maketrans(_ROTATED, _PLAIN)

ADDRESS = re.compile(r"(?<![\w.+-])([\w.+-]+)(?:@|%40)([\w-]+(?:\.[\w-]+)+)")
NEXT_PART = "-------------- next part --------------"
ATTACHMENT = re.compile(
    r'(?is)<p><strong>Attachment:\s*<a href="([^"]+)"\s*><tt>(.*?)</tt></a></strong>'
    r'(?:<br>\s*<em>Description:</em>(.*?))?</p>')
INNERMOST_QUOTE = re.compile(r"(?is)<blockquote[^>]*>((?:(?!<blockquote).)*?)</blockquote>")


def obscure(text):
    """Every address written "user at domain", a relayed one with two @ too."""
    while True:
        written = ADDRESS.sub(r"\1 at \2", text)
        if written == text:
            return text
        text = written


def encoded(value):
    """A header value, as RFC 2047 encoded words when it is not ASCII."""
    if value.isascii():
        return value
    return Header(value, "utf-8").encode(maxlinelen=998)


def text_of(markup):
    """Markup as text: preformatted parts as written, the rest as HTML."""
    parts, pos = [], 0
    for m in re.finditer(r"(?is)<pre[^>]*>(.*?)</pre>", markup):
        parts += [html_to_text(markup[pos:m.start()]), strip_tags(m.group(1))]
        pos = m.end()
    parts.append(html_to_text(markup[pos:]))
    return "".join(parts)


def body_of(page):
    """The message's text as MHonArc shows it, attachments named after
    Mailman's "next part" line."""
    markup = section(page, "Body-of-Message")

    def attachment(m):
        lines = [NEXT_PART, "An attachment was scrubbed...", f"Name: {strip_tags(m.group(2)).strip()}"]
        if m.group(3) and m.group(3).strip():
            lines.append(f"Desc: {' '.join(strip_tags(m.group(3)).split())}")
        return "\0" + "\n".join(lines) + "\n\0"

    markup = ATTACHMENT.sub(attachment, markup)
    # A message written in HTML quotes in a <blockquote>: its lines get the
    # "> " a plain text reply gives them, innermost quote first.
    while True:
        m = INNERMOST_QUOTE.search(markup)
        if m is None:
            break
        quoted = "\n".join(f"> {line}".rstrip() for line in text_of(m.group(1)).strip("\n").split("\n"))
        markup = markup[:m.start()] + "<pre>" + html.escape(quoted, quote=False) + "\n</pre>" + markup[m.end():]
    text = text_of(markup).replace("\r\n", "\n").replace("\r", "\n").replace("\0", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text.strip("\n")) + "\n"
    return re.sub(r"(?m)^(>*From )", r">\1", obscure(text))


def sent(page, head):
    """When the message was sent, at the offset it gave: its Date header,
    else the time the list got it. A zone given by a name Python does not
    know is taken for UTC, and a three-digit year counts from 1900, as RFC
    5322 reads one (mailers of 2000 that wrote the year as 100)."""
    for value in (head.get("date", ""), dict(comments(page)).get("Date", "")):
        try:
            when = parsedate_to_datetime(re.sub(r"\s*\([^()]*\)?$", "", value))
        except (TypeError, ValueError, IndexError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when.year < 1000:
            when = when.replace(year=when.year + 1900)
        return when
    return None


def convert(page, fallback):
    """A message page as an mbox entry, pipermail's way, and its Message-ID."""
    head = fields(page)
    notes = comments(page)
    raw_from = next((v for k, v in notes if k == "From-R13"), "").translate(UNROT13)
    pairs = getaddresses([str(make_header(decode_header(raw_from))) if raw_from else head.get("from", "")])
    name, addr = pairs[0] if pairs else ("", "")
    local, _, domain = addr.partition("@")
    who = f"{local} at {domain}" if domain else (obscure(local) or "unknown")
    name = obscure(" ".join(name.split()))
    when = sent(page, head) or fallback
    utc = when.astimezone(timezone.utc)
    stamp = utc.strftime("%a %b ") + f"{utc.day:2d}" + utc.strftime(" %H:%M:%S %Y")
    lines = [f"From {who}  {stamp}", f"From: {who} ({encoded(name)})" if name else f"From: {who}"]
    lines.append(f"Date: {format_datetime(when)}")
    subject = head.get("subject") or next((v for k, v in notes if k == "Subject"), "")
    lines.append(f"Subject: {encoded(obscure(' '.join(subject.split())))}")
    reply = ids(head.get("in-reply-to", ""))
    if reply:
        lines.append(f"In-Reply-To: <{reply[0]}>")
    references = [f"<{v}>" for k, v in notes if k == "Reference"]
    if references:
        lines.append(f"References: {' '.join(references)}")
    message_id = next((v for k, v in notes if k == "Message-Id"), "")
    if message_id:
        lines.append(f"Message-ID: <{message_id}>")
    return "\n".join(lines) + "\n\n" + body_of(page) + "\n", message_id


def last_month(list_dir):
    """The month config.json names in until, or None to keep every month."""
    return json.loads((list_dir / "config.json").read_text()).get("until")


def build(list_dir):
    cache = list_dir / ".cache"
    raw = list_dir / "raw"
    raw.mkdir(exist_ok=True)
    # Written afresh, so a month left out since the last build goes; add's files stay.
    for old in raw.glob("*.mbox"):
        if not old.name.startswith("from-"):
            old.unlink()
    until = last_month(list_dir)
    total = missing = later = 0
    for month_dir in sorted(p for p in cache.iterdir() if p.is_dir()):
        month = month_dir.name
        y, m = map(int, month.split("-"))
        fallback = datetime(y, m, 1, tzinfo=timezone.utc)
        pages = sorted(month_dir.glob("msg*.html"))
        entries = []
        for p in pages:
            text = page_text(p)
            if until and (sent(text, fields(text)) or fallback).astimezone(timezone.utc).strftime("%Y-%m") > until:
                later += 1
            else:
                entries.append(convert(text, fallback)[0])
        if entries:
            (raw / f"{y}-{MONTHS[m - 1]}.mbox").write_text("".join(entries), encoding="utf-8")
        if until and month > until:
            continue
        named = set()
        for index in ("index.html", "threads.html"):
            if (month_dir / index).exists():
                named |= set(re.findall(r'href="(msg\d+\.html)"', page_text(month_dir / index)))
        lost = sorted(named - {p.name for p in pages})
        total += len(entries)
        missing += len(lost)
        print(f"{month}: {len(entries)} messages" + (f", {len(lost)} its index names were never saved" if lost else ""))
    print(f"{list_dir.name}: {total} messages; {missing} more named by the month indexes were never saved"
          + (f"; {later} sent after {until} left out" if until else ""))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

START = re.compile(r"(?m)^(?=From \S+(?: at \S+)?  \w{3} \w{3} [ \d]\d \d\d:\d\d:\d\d \d{4}$)")
MESSAGE_ID = re.compile(r"(?mi)^Message-ID:\s*<([^<>\s]+)>")
DATE = re.compile(r"(?mi)^Date:[ \t]*(.+)$")


def month_sent(headers):
    """The month (YYYY-MM, UTC) an mbox entry was sent in: its Date header,
    else the date on its From line."""
    found = DATE.search(headers)
    try:
        when = parsedate_to_datetime(re.sub(r"\s*\([^()]*\)$", "", found.group(1).strip()))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return when.astimezone(timezone.utc).strftime("%Y-%m")
    except (AttributeError, TypeError, ValueError, IndexError):
        stamp = headers.partition("\n")[0].split()[-5:]
        return datetime.strptime(" ".join(stamp), "%a %b %d %H:%M:%S %Y").strftime("%Y-%m")


def messages(text):
    return [m for m in START.split(text) if m.startswith("From ")]


def add(list_dir, other):
    raw = list_dir / "raw"
    have = set()
    for path in raw.glob("*.mbox"):
        if not path.name.startswith("from-"):
            have |= set(MESSAGE_ID.findall(path.read_text(encoding="utf-8")))
    until = last_month(list_dir)
    kept, later = [], 0
    for message in messages(other.read_text(encoding="utf-8")):
        headers = message.partition("\n\n")[0]
        if until and month_sent(headers) > until:
            later += 1
            continue
        found = MESSAGE_ID.search(headers)
        if found is None or found.group(1) not in have:
            kept.append(message if message.endswith("\n\n") else message.rstrip("\n") + "\n\n")
    name = re.sub(r"\.mbox$", "", other.name)
    (raw / f"from-{name}.mbox").write_text("".join(kept), encoding="utf-8")
    print(f"{list_dir.name}: {len(kept)} messages from {other.name} that raw/ did not have"
          + (f"; {later} sent after {until} left out" if until else ""))


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("fetch", "build", "add") or (sys.argv[1] == "add") != (len(sys.argv) == 4):
        raise SystemExit(__doc__)
    list_dir = Path(__file__).resolve().parent.parent / sys.argv[2]
    if not (list_dir / "config.json").exists():
        raise SystemExit(f"No such list: {sys.argv[2]}")
    if sys.argv[1] == "fetch":
        fetch(list_dir)
    elif sys.argv[1] == "build":
        build(list_dir)
    else:
        add(list_dir, Path(sys.argv[3]))


if __name__ == "__main__":
    main()
