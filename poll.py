"""Deprecated module.

The custom poll engine now lives in :mod:`app.polls` (rendering, single-select
voting, live menu edits, grouped results).  This shim keeps ``import poll``
working for any old references.
"""

from app.polls import (  # noqa: F401
    apply_menu_change,
    describe_change,
    get_day,
    poll_header,
    poll_keyboard,
    register_poll,
    results_text,
    set_vote,
    start_day,
    toggle_vote,
    user_votes,
)
