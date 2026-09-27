from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.intelligence.social_cooccurrence import SocialCoOccurrenceFilter


def test_one_to_ten_minute_window_boundaries() -> None:
    event_time = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    filter_ = SocialCoOccurrenceFilter()

    assert filter_.min_delay == timedelta(minutes=1)
    assert filter_.max_delay == timedelta(minutes=10)
    assert event_time + filter_.min_delay <= event_time + timedelta(minutes=1)
    assert event_time + timedelta(minutes=10) <= event_time + filter_.max_delay


def test_window_excludes_posts_before_one_minute() -> None:
    event_time = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    post_time = event_time + timedelta(seconds=59)
    assert not (
        event_time + timedelta(minutes=1)
        <= post_time
        <= event_time + timedelta(minutes=10)
    )


def test_window_excludes_posts_after_ten_minutes() -> None:
    event_time = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    post_time = event_time + timedelta(minutes=10, seconds=1)
    assert not (
        event_time + timedelta(minutes=1)
        <= post_time
        <= event_time + timedelta(minutes=10)
    )


def test_filter_rejects_invalid_window() -> None:
    try:
        SocialCoOccurrenceFilter(
            min_delay=timedelta(minutes=10),
            max_delay=timedelta(minutes=1),
        )
    except ValueError as exc:
        assert "max_delay" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_filter_validates_event_id() -> None:
    filter_ = SocialCoOccurrenceFilter()
    try:
        filter_.evaluate_buy_event(0)
    except ValueError as exc:
        assert "buy_event_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
