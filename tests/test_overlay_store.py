import pytest

from app.core.subtitle_overlay.store import OverlayStore


def test_edit_revokes_approval_after_reopen(tmp_path):
    path = tmp_path / 'overlay.sqlite3'
    store = OverlayStore(path)
    first = store.save('a', {'y': 900})
    store.approve('a', first)
    assert store.is_approved('a', first)
    assert store.save('a', {'y': 900}) == first
    second = store.save('a', {'y': 920})
    reopened = OverlayStore(path)
    assert second > first
    assert reopened.load('a')['payload']['y'] == 920
    assert not reopened.is_approved('a', first)
    assert not reopened.is_approved('a', second)
    with pytest.raises(ValueError):
        reopened.approve('a', first)


def test_blocked_and_rendering_revisions_cannot_be_changed(tmp_path):
    store = OverlayStore(tmp_path / 'state.db')
    rev = store.save('a', {'blocking': ['collision']})
    with pytest.raises(ValueError):
        store.approve('a', rev)
    rev = store.save('a', {'blocking': []})
    with pytest.raises(ValueError):
        store.set_state('a', rev, 'rendering')
    store.approve('a', rev)
    store.set_state('a', rev, 'rendering')
    with pytest.raises(ValueError):
        store.save('a', {'y': 9})
    store.set_state('a', rev, 'failed')
    assert store.save('a', {'y': 9}) > rev


def test_ordered_batch_survives_reopen(tmp_path):
    path = tmp_path / 'state.db'
    store = OverlayStore(path)
    store.save_batch('batch', ('b', 'a'), {'width': 1920})
    assert OverlayStore(path).load_batch('batch')['source_ids'] == ['b', 'a']
    with pytest.raises(ValueError):
        store.save_batch('batch', ('a', 'a'), {})
