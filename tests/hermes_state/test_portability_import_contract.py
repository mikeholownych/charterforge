"""Pin the _PREVIEW_RAW_SUBQUERY_SQL contract hermes_state_portability._rich_select depends on.

hermes_state_common must export the correlated preview subquery as a
SELECT-list expression (not a bare CASE body): correlated on s.id, user-role,
eligible content, timestamp/id ordering, COALESCE-fallback, _preview_raw alias.
"""
from __future__ import annotations

import hermes_state_common as hc


def test_preview_raw_subquery_exists_and_is_correlated():
    sql = hc._PREVIEW_RAW_SUBQUERY_SQL
    assert "m.session_id = s.id" in sql
    assert "m.role = 'user'" in sql
    assert "m.content IS NOT NULL" in sql
    assert hc._PREVIEW_ELIGIBLE_SQL in sql
    assert "ORDER BY m.timestamp, m.id LIMIT 1" in sql
    assert "COALESCE(" in sql
    assert "AS _preview_raw" in sql


def test_rich_select_interpolates_subquery():
    from hermes_state_portability import _rich_select

    rendered = _rich_select("s.id, s.title", "1=1")
    assert hc._PREVIEW_RAW_SUBQUERY_SQL in rendered
