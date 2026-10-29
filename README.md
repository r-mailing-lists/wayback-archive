# wayback-archive

Archives of R mailing lists whose own hosts are gone, rebuilt from the copies the Internet Archive's [Wayback Machine](https://web.archive.org/) saved of their monthly archive files. They are pooled into one repository and laid out like the other archives in [r-mailing-lists](https://github.com/r-mailing-lists).

| List | What it was | Where it lived |
|---|---|---|
| `amelia` | Amelia II, multiple imputation of missing data | Harvard (Gary King's lists), `lists.gking.harvard.edu/pipermail/amelia/` |
| `relogit` | ReLogit, logistic regression for rare events | Harvard (Gary King's lists), `lists.gking.harvard.edu/pipermail/relogit/` |

See [`lists.tsv`](lists.tsv) for message counts and date ranges.

Gary King's group at Harvard ran a Mailman list for each of its R packages. Zelig, MatchIt and WhatIf reached Gmane and are in [gmane-archive](https://github.com/r-mailing-lists/gmane-archive); Amelia and ReLogit never did. Their server no longer answers, and Amelia's questions moved to GitHub Discussions. The Wayback Machine saved each month's `.txt.gz` file in June 2013, so what is here is the archive as Mailman served it then.

Amelia's archive index of June 2013 names 118 months, from April 2002 to May 2013. The Wayback Machine never saved four of them: September 2003, November 2004, September 2012 and May 2013. ReLogit's index names 35 months, all saved.

## How it is collected

`tools/wayback.py fetch <list>` asks the Wayback Machine's capture index for every file under the list's original archive and takes the newest capture of each month's `.txt.gz` (or of the plain `.txt` when no `.gz` was saved). It downloads each file once, unchanged, one request at a time with a pause between them, unzips it to `<list>/raw/<Year>-<Month>.mbox`, and records in `<list>/wayback.json` which capture the month came from and the SHA-256 of what was written. A later run fetches only the months `wayback.json` does not name.

Mailman wrote each sender as `user at example.org` in these files. Message text is kept as the archive showed it, as on the R Project's own lists. `python3 tools/wayback.py check <list>` counts whole addresses in message text, saying where but not what.

## Structure

Each list has its own directory:

- `<list>/config.json` - list name, description, and its original archive (`source_url`)
- `<list>/wayback.json` - the capture each month's file came from
- `<list>/raw/` - one Mailman .mbox file per month, as the Wayback Machine saved it
- `<list>/processed/` - structured JSON from [rmail-parser](https://github.com/r-mailing-lists/rmail-parser), one file per month
- `<list>/meta.json` - list statistics

`lists.tsv` at the top level indexes all lists.

## Updating

The lists are closed, so nothing new arrives. The **Update Archive** workflow runs daily and only re-parses `raw/`, so the archive follows rmail-parser's releases. Locally:

``` bash
RMAIL_PARSER=/path/to/rmail-parser tools/update.sh
```

To add a list, create `<list>/config.json` with its original archive in `source_url`, run `python3 tools/wayback.py fetch <list>`, then `tools/update.sh <list>`. `python3 tools/wayback_test.py` runs the tests.
