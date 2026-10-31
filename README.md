# wayback-archive

Archives of R mailing lists whose own archives are gone or closed, rebuilt from the copies the Internet Archive's [Wayback Machine](https://web.archive.org/) saved of them. They are pooled into one repository and laid out like the other archives in [r-mailing-lists](https://github.com/r-mailing-lists).

| List | What it was | Where it lived |
|---|---|---|
| `amelia` | Amelia II, multiple imputation of missing data | Harvard (Gary King's lists), `lists.gking.harvard.edu/pipermail/amelia/` |
| `relogit` | ReLogit, logistic regression for rare events | Harvard (Gary King's lists), `lists.gking.harvard.edu/pipermail/relogit/` |
| `s-news` | S-news, the S and S-PLUS users' list, through 2010 | Washington University in St. Louis, `www.biostat.wustl.edu/archives/html/s-news/` |

See [`lists.tsv`](lists.tsv) for message counts and date ranges.

Gary King's group at Harvard ran a Mailman list for each of its R packages. Zelig, MatchIt and WhatIf reached Gmane and are in [gmane-archive](https://github.com/r-mailing-lists/gmane-archive); Amelia and ReLogit never did. Their server no longer answers, and Amelia's questions moved to GitHub Discussions. The Wayback Machine saved each month's `.txt.gz` file in June 2013, so what is here is the archive as Mailman served it then.

Amelia's archive index of June 2013 names 118 months, from April 2002 to May 2013. The Wayback Machine never saved four of them: September 2003, November 2004, September 2012 and May 2013. ReLogit's index names 35 months, all saved.

S-news was the list of the S and S-PLUS community that R grew out of. Washington University's biostatistics division archived it with MHonArc, a web page per message and no mbox to download. The list still runs, but its owners have closed its web archive, so only messages sent through December 2010 are here. The Wayback Machine saved some 23,000 of its message pages from 1998 to 2010, and the month indexes name about 600 more it never saved. Gmane's copy of the list, which starts in 2006, adds the messages from 2006 to 2010 that the saved pages lack. The pages were read once, in October 2026, and will not be read again: the list is closed here, and `s-news/wayback.json` records which capture each page came from.

Two things were repaired on the way, both from what the archive itself shows. About 60 messages came from senders whose clocks were wrong, some by decades; each is dated as the message that reached the archive before it, and its raw entry keeps the sender's date in `X-Original-Date`. About 2,800 replies were sent without the headers that tie a reply to its question; each now follows up the message MHonArc's thread index for the month showed it under.

## How it is collected

`tools/wayback.py fetch <list>` asks the Wayback Machine's capture index for every file under the list's original archive and takes the newest capture of each month's `.txt.gz` (or of the plain `.txt` when no `.gz` was saved). It downloads each file once, unchanged, one request at a time with a pause between them, unzips it to `<list>/raw/<Year>-<Month>.mbox`, and records in `<list>/wayback.json` which capture the month came from and the SHA-256 of what was written. A later run fetches only the months `wayback.json` does not name.

Mailman wrote each sender as `user at example.org` in these files. Message text is kept as the archive showed it, as on the R Project's own lists. `python3 tools/wayback.py check <list>` counts whole addresses in message text, saying where but not what.

A list archived with MHonArc, as S-news was, is collected with `tools/mhonarc.py` instead. `fetch <list>` reads every message page and month index the Wayback Machine saved under the list's archive, one request at a time with a pause between them. The pages hold plain addresses, so they stay in `<list>/.cache/`, which git ignores, and `<list>/wayback.json` records the capture each page came from. `build <list>` writes `<list>/raw/` from them as Mailman's text archives would read: the From, Date, Subject, In-Reply-To, References and Message-ID headers, every address written `user at example.org`, and each date in RFC 2822's form. A message dated more than a week outside the month it arrived in takes the date of the one that arrived before it, a reply that names no message it follows up gets the one the month's thread index shows it under, and a message delivered twice is written once. `add <list> <mbox>` writes the messages of another copy that `raw/` lacks to `raw/from-<name>.mbox`. When `config.json` names a last month in `until`, both leave out everything sent after it.

## Structure

Each list has its own directory:

- `<list>/config.json` - list name, description, and its original archive (`source_url`)
- `<list>/wayback.json` - the capture each month's file (or each MHonArc page) came from
- `<list>/raw/` - one Mailman .mbox file per month, as the Wayback Machine saved it or as `tools/mhonarc.py` rebuilt it, and `from-<name>.mbox` for messages from another copy
- `<list>/processed/` - structured JSON from [rmail-parser](https://github.com/r-mailing-lists/rmail-parser), one file per month
- `<list>/meta.json` - list statistics

`lists.tsv` at the top level indexes all lists.

## Updating

The lists are closed, so nothing new arrives. The **Update Archive** workflow runs daily and only re-parses `raw/`, so the archive follows rmail-parser's releases. Locally:

``` bash
RMAIL_PARSER=/path/to/rmail-parser tools/update.sh
```

To add a list, create `<list>/config.json` with its original archive in `source_url`, run `python3 tools/wayback.py fetch <list>` (or, for MHonArc, `tools/mhonarc.py fetch` and `build`), then `tools/update.sh <list>`. `python3 tools/wayback_test.py` and `python3 tools/mhonarc_test.py` run the tests.
