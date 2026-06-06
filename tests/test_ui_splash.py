"""Tests for splash screen rendering and timing helpers."""

from renderkit.ui.splash_screen import (
    SPLASH_MIN_DURATION_MS,
    compute_remaining_splash_ms,
    create_splash_screen,
)


def test_compute_remaining_splash_ms_partial_elapsed():
    """Return positive remaining duration when minimum time is not reached."""
    remaining = compute_remaining_splash_ms(started_at=10.0, minimum_ms=1200, now=10.5)
    assert remaining == 700


def test_compute_remaining_splash_ms_elapsed_exceeds_minimum():
    """Return zero when elapsed time already exceeds minimum duration."""
    remaining = compute_remaining_splash_ms(
        started_at=10.0,
        minimum_ms=SPLASH_MIN_DURATION_MS,
        now=11.5,
    )
    assert remaining == 0


def test_create_splash_screen_returns_valid_pixmap(qapp):
    """Create a splash screen with a valid default pixmap size."""
    splash = create_splash_screen("0.0.0")
    pixmap = splash.pixmap()
    assert pixmap.isNull() is False
    assert pixmap.width() == 620
    assert pixmap.height() == 320
    splash.close()
