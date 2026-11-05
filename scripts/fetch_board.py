"""Refresh data/board.json (Board of Governors) and data/calendar.json (scheduled FOMC meetings)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fed_decoder.data.calendar import save_calendar
from fed_decoder.data.leadership import save_board

if __name__ == "__main__":
    b = save_board()
    print(", ".join(f"{m['name']} ({m['title']})" for m in b["members"]))
    c = save_calendar()
    print(f"calendar: {len(c['meetings'])} scheduled meetings")
