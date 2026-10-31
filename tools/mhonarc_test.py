"""Tests for mhonarc.py: run with python3 -I tools/mhonarc_test.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mhonarc  # noqa: E402

ROT13 = str.maketrans(mhonarc._PLAIN, mhonarc._ROTATED)


def page(message_id="199803021600.KAA01234@mail.example.com", date="Mon, 2 Mar 1998 10:00:00 -0600",
         subject="Re: [S] lm question", body="<pre>\nTry lm(y ~ x).\n</pre>\n"):
    """A message page as MHonArc 2.6 writes one."""
    sender = "Joe Bloggs <joe.bloggs@example.com>"
    return f"""<!-- MHonArc v2.6.8 -->
<!--X-Subject: {subject} -->
<!--X-From-R13: {sender.translate(ROT13).replace('<', '&lt;').replace('>', '&gt;')} -->
<!--X-Date: {date} -->
<!--X-Message-Id: {message_id} -->
<!--X-Content-Type: text/plain -->
<!--X-Reference: 199803011200.AAA00001@mail.example.org -->
<!--X-Head-End-->
<html><head><title>{subject}</title></head><body>
<!--X-Head-of-Message-->
<ul>
<li><em>To</em>: s-news at wubios.wustl.edu</li>
<li><em>Subject</em>: {subject}</li>
<li><em>From</em>: Joe Bloggs &lt;joe.bloggs@example.com&gt;</li>
<li><em>Date</em>: {date}</li>
<li><em>In-reply-to</em>: &lt;199803011200.AAA00001@mail.example.org&gt;</li>
</ul>
<!--X-Head-of-Message-End-->
<!--X-Head-Body-Sep-Begin-->
<hr>
<!--X-Head-Body-Sep-End-->
<!--X-Body-of-Message-->
{body}<!--X-Body-of-Message-End-->
</body></html>
"""


FALLBACK = datetime(1998, 3, 1, tzinfo=timezone.utc)


class Convert(unittest.TestCase):
    def test_writes_pipermails_headers_with_the_sender_written_at(self):
        entry, message_id = mhonarc.convert(page(), FALLBACK)
        head = entry.partition("\n\n")[0].split("\n")
        self.assertEqual(head, [
            "From joe.bloggs at example.com  Mon Mar  2 16:00:00 1998",
            "From: joe.bloggs at example.com (Joe Bloggs)",
            "Date: Mon, 02 Mar 1998 10:00:00 -0600",
            "Subject: Re: [S] lm question",
            "In-Reply-To: <199803011200.AAA00001@mail.example.org>",
            "References: <199803011200.AAA00001@mail.example.org>",
            "Message-ID: <199803021600.KAA01234@mail.example.com>",
        ])
        self.assertEqual(message_id, "199803021600.KAA01234@mail.example.com")

    def test_writes_every_address_in_the_text_at_and_escapes_from_lines(self):
        body = "<pre>\nMail me at jane.doe@example.org, or\nFrom the help page: x%40example.net\n</pre>\n"
        entry = mhonarc.convert(page(body=body), FALLBACK)[0]
        text = entry.partition("\n\n")[2]
        self.assertEqual(text, "Mail me at jane.doe at example.org, or\n>From the help page: x at example.net\n\n")

    def test_writes_a_relayed_address_with_two_ats_at_twice(self):
        body = "<pre>\nJane.Doe@host.example@mail.example.gov\n</pre>\n"
        text = mhonarc.convert(page(body=body), FALLBACK)[0].partition("\n\n")[2]
        self.assertEqual(text, "Jane.Doe at host.example at mail.example.gov\n\n")

    def test_names_an_attachment_as_mailmans_next_part_line(self):
        body = ('<pre>\nSee the file.\n</pre>\n<p><strong>Attachment: <a href="bin00001.bin" ><tt>data.csv</tt></a></strong>'
                '<br>\n<em>Description:</em> the data</p>\n')
        text = mhonarc.convert(page(body=body), FALLBACK)[0].partition("\n\n")[2]
        self.assertEqual(text, "See the file.\n\n-------------- next part --------------\n"
                               "An attachment was scrubbed...\nName: data.csv\nDesc: the data\n\n")

    def test_writes_a_date_the_parser_could_not_read_in_rfc_2822s_form(self):
        for written, date in [("Tue, 23 Mar 1999 10:00:00 HST", "Tue, 23 Mar 1999 10:00:00 +0000"),
                              ("Thu, 11 Mar 1999 10:00:00 -600", "Thu, 11 Mar 1999 10:00:00 -0600"),
                              ("Thu, 12 Jun 2003 10:00:00 +0200 (METDST", "Thu, 12 Jun 2003 10:00:00 +0200"),
                              ("zo, 15 aug 1999 10:00:00", "Sun, 15 Aug 1999 10:00:00 +0000"),
                              # a mailer of 2000 that wrote the year as 100
                              ("Mon, 28 Feb 100 10:00:00 -0700 (MST)", "Mon, 28 Feb 2000 10:00:00 -0700")]:
            entry = mhonarc.convert(page(date=written), FALLBACK)[0]
            self.assertIn(f"\nDate: {date}\n", entry, written)

    def test_takes_the_months_first_day_for_a_message_without_a_date(self):
        entry = mhonarc.convert(page(date="sometime in March"), FALLBACK)[0]
        self.assertTrue(entry.startswith("From joe.bloggs at example.com  Sun Mar  1 00:00:00 1998\n"))
        self.assertIn("\nDate: Sun, 01 Mar 1998 00:00:00 +0000\n", entry)


def list_dir(root, config):
    d = Path(root) / "a-list"
    d.mkdir()
    (d / "config.json").write_text(json.dumps(config))
    return d


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()):
        fn(*args)


class Build(unittest.TestCase):
    def test_keeps_only_the_messages_sent_until_the_configs_last_month(self):
        with tempfile.TemporaryDirectory() as root:
            d = list_dir(root, {"list": "a-list", "until": "2010-12"})
            for month, n, date in [("2010-12", "msg00000", "Thu, 30 Dec 2010 12:00:00 +0000"),
                                   # filed in December, sent in January by the clock of UTC
                                   ("2010-12", "msg00001", "Fri, 31 Dec 2010 23:30:00 -0600"),
                                   ("2011-09", "msg00000", "Thu, 1 Sep 2011 12:00:00 +0000")]:
                (d / ".cache" / month).mkdir(parents=True, exist_ok=True)
                (d / ".cache" / month / f"{n}.html").write_text(page(message_id=f"{month}-{n}@x.example", date=date))
            quiet(mhonarc.build, d)
            self.assertEqual(sorted(p.name for p in (d / "raw").iterdir()), ["2010-December.mbox"])
            self.assertEqual(mhonarc.MESSAGE_ID.findall((d / "raw" / "2010-December.mbox").read_text()),
                             ["2010-12-msg00000@x.example"])

    def test_keeps_every_month_when_the_config_names_no_last_month(self):
        with tempfile.TemporaryDirectory() as root:
            d = list_dir(root, {"list": "a-list"})
            (d / ".cache" / "2011-09").mkdir(parents=True)
            (d / ".cache" / "2011-09" / "msg00000.html").write_text(page(date="Thu, 1 Sep 2011 12:00:00 +0000"))
            quiet(mhonarc.build, d)
            self.assertEqual(sorted(p.name for p in (d / "raw").iterdir()), ["2011-September.mbox"])


def mbox_entry(message_id, date):
    return (f"From x at example.com  Thu Dec 30 12:00:00 2010\nFrom: x at example.com\nDate: {date}\n"
            f"Subject: a question\nMessage-ID: <{message_id}>\n\nThe text.\n\n")


class Add(unittest.TestCase):
    def test_adds_the_messages_raw_lacks_that_were_sent_until_the_last_month(self):
        with tempfile.TemporaryDirectory() as root:
            d = list_dir(root, {"list": "a-list", "until": "2010-12"})
            (d / "raw").mkdir()
            (d / "raw" / "2010-December.mbox").write_text(mbox_entry("have@x.example", "Thu, 30 Dec 2010 12:00:00 +0000"))
            other = Path(root) / "gmane.mbox"
            other.write_text(mbox_entry("have@x.example", "Thu, 30 Dec 2010 12:00:00 +0000")
                             + mbox_entry("new@x.example", "Fri, 31 Dec 2010 12:00:00 +0000")
                             + mbox_entry("late@x.example", "Fri, 31 Dec 2010 23:30:00 -0600")
                             + mbox_entry("later@x.example", "Sun, 2 Jan 2011 12:00:00 +0000"))
            quiet(mhonarc.add, d, other)
            self.assertEqual(mhonarc.MESSAGE_ID.findall((d / "raw" / "from-gmane.mbox").read_text()),
                             ["new@x.example"])


if __name__ == "__main__":
    unittest.main()
