import xml.etree.ElementTree as ET
from datetime import date

from fed_decoder.data.feed import parse

SAMPLE = """<rss><channel>
<item><title>Federal Reserve issues FOMC statement</title><link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261209a.htm</link></item>
<item><title>Federal Reserve Board announces approval of application by Example Bank</title><link>https://www.federalreserve.gov/newsevents/pressreleases/orders20261201a.htm</link></item>
<item><title>Minutes of the Federal Open Market Committee, October 27-28, 2026</title><link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261118a.htm</link></item>
<item><title>Federal Reserve issues FOMC statement</title><link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20261116a.htm</link></item>
</channel></rss>"""


def test_feed_finds_scheduled_and_unscheduled_statements_only():
    links = parse(ET.fromstring(SAMPLE))
    assert [l.meeting_date for l in links] == [date(2026, 12, 9), date(2026, 11, 16)]  # minutes and orders are ignored
    assert links[0].url.endswith("monetary20261209a.htm")
