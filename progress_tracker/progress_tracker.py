from datetime import datetime, timedelta

from progress_tracker.timeout import Timeout
from typing import Any, Callable, Dict, Generic, Iterable, Optional, Sized, Type, TypeVar, cast
from types import TracebackType

T = TypeVar("T")


def default_format_callback(**kwargs: Optional[str]) -> str:
    i = kwargs["i"]
    total = kwargs["total"]
    if total is None or i == total:
        format_string = "{i} in {time_taken}"
    else:
        format_string = "{i}/{total} ({percent_complete}%) in {time_taken} (Time left: {estimated_time_remaining})"

    return format_string.format(**kwargs)


class ProgressTracker(Generic[T]):
    # This is a class that allows you to offload the tracking of progress.
    # It encapsulates a number of common conditions for reporting progress.
    #
    # For example, you often want to print out your processing progress every x percent of completion, but also every y seconds.
    # This class allows you to not have to do all of this tracking in your code. It will call its callback function with a formatted string.
    #
    def __init__(self, iterable: Iterable[T],
                 total: Optional[int] = None,
                 callback: Callable[[str], Any] = print,
                 format_callback: Callable[..., str] = default_format_callback,
                 every_n_percent: Optional[float] = None,
                 every_n_records: Optional[int] = None,
                 every_n_seconds: Optional[float] = None,
                 every_n_seconds_idle: Optional[float] = None,
                 report_first_record: bool = False,
                 report_last_record: bool = False) -> None:

        self.iterable = iterable

        self.total: Optional[int]
        try:
            self.total = len(cast(Sized, self.iterable))
        except TypeError:
            self.total = None

        if self.total is None and total is not None:
            self.total = total

        if self.total is None:
            if every_n_percent is not None:
                raise Exception("Cannot ask to report 'every_n_percent' if total length is not available")

        self.callback = callback
        self.format_callback = format_callback

        self.every_n_percent = every_n_percent
        self.next_percent = 0 if report_first_record else every_n_percent

        self.every_n_records = every_n_records
        self.next_record_count = 0 if report_first_record else every_n_records

        self.timeout = Timeout(timedelta(seconds=every_n_seconds)) if every_n_seconds is not None else None
        self.idle_timeout = Timeout(timedelta(seconds=every_n_seconds_idle)) if every_n_seconds_idle is not None else None

        self.report_last_record = report_last_record

        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.total_time: Optional[timedelta] = None

        self.items_seen = 0
        self.times_callback_called = 0

    def __iter__(self) -> Iterable[T]:
        with self:
            for index, item in enumerate(self.iterable):
                self.items_seen += 1
                yield item
                check = self.check(index + 1)
                if check is not None:
                    self.callback(self.format_callback(**check))
                    self.times_callback_called += 1

    def __enter__(self) -> None:
        self.start_time = datetime.utcnow()

    def __exit__(self, exc_type: Optional[Type[Exception]], value: Optional[Exception], traceback: Optional[TracebackType]) -> None:
        self.complete()

    def should_report(self, i: int) -> bool:
        should_report = False
        if self.timeout is not None and self.timeout.is_overdue():
            should_report = True
            self.timeout.reset()
        if self.idle_timeout is not None and self.idle_timeout.is_overdue():
            should_report = True
        if self.total is not None and self.every_n_percent is not None and self.next_percent is not None:
            percent_complete = (i / self.total) * 100
            if percent_complete >= self.next_percent:
                should_report = True
                self.next_percent = ((int(percent_complete) // self.every_n_percent) + 1) * self.every_n_percent
        if self.every_n_records is not None and self.next_record_count is not None and i >= self.next_record_count:
            should_report = True
            self.next_record_count = ((i // self.every_n_records) + 1) * self.every_n_records
        if self.total is not None and self.report_last_record and i == self.total:
            should_report = True

        return should_report

    # Returns a tuple that contains all of the usual values that you want to print out.
    def check(self, i: int) -> Optional[Dict[str, Any]]:
        assert self.start_time is not None
        result: Optional[Dict[str, Any]]
        if self.should_report(i):
            time_taken = datetime.utcnow() - self.start_time
            percent_complete: Optional[float]
            estimated_time_remaining: Optional[timedelta]
            if self.total is not None:
                percent_complete = (i / self.total) * 100
                estimated_time_remaining = timedelta(seconds=((100 - percent_complete) / percent_complete) * time_taken.total_seconds()) if percent_complete != 0 else None
            else:
                percent_complete = None
                estimated_time_remaining = None

            items_per_second = i / time_taken.total_seconds() if time_taken.total_seconds() != 0 else None

            result = {
                'i': i,
                'total': self.total,
                'percent_complete': percent_complete,
                'time_taken': time_taken,
                'estimated_time_remaining': estimated_time_remaining,
                'items_per_second': items_per_second
            }
        else:
            result = None

        if self.idle_timeout is not None:
            self.idle_timeout.reset()

        return result

    def complete(self) -> None:
        assert self.start_time is not None
        self.end_time = datetime.utcnow()
        self.total_time = self.end_time - self.start_time


def track_progress(iterable: Iterable[T], **kwargs: Any) -> ProgressTracker[T]:
    return ProgressTracker(iterable, **kwargs)
