import pytest
from PySide6.QtWidgets import QApplication
from app.ui.overlay_review import OverlayReviewView


def test_review_blocks_bad_rows_and_emits_revision_bound_approval():
    app = QApplication.instance() or QApplication([])
    view = OverlayReviewView()
    row = {'id':'a', 'name':'a.mp4', 'revision':3, 'approved':None, 'state':'review', 'payload':{
        'layout': {'y':300,'fallback':True}, 'blocking':['collision'], 'previews':[], 'warnings':[]}}
    view.show_sources([row])
    assert not view.approve_button.isEnabled()
    row['payload']['blocking'] = []
    row['payload']['previews'] = [{'path':'missing.png', 'timestamp_ms':i*1000, 'sample_text':False} for i in range(5)]
    view.show_sources([row])
    assert not view.approve_button.isEnabled()
    view.fallback_confirm.setChecked(True)
    assert view.approve_button.isEnabled()
    approvals=[]
    view.approve_requested.connect(lambda *args: approvals.append(args))
    view.approve_button.click()
    assert approvals == [('a',3,True)]
    assert not view.render_button.isEnabled()
    row['approved'] = 3
    view.show_sources([row])
    assert view.render_button.isEnabled()
    view.close()


def test_review_can_change_dubbing_for_saved_source():
    app = QApplication.instance() or QApplication([])
    view = OverlayReviewView()
    view.show_sources([{'id':'a', 'revision':3, 'approved':3, 'state':'approved',
        'dub_enabled':True, 'payload':{}}])
    changes = []
    view.dubbing_changed.connect(lambda *args: changes.append(args))
    assert view.dub_enabled.isChecked()
    view.dub_enabled.setChecked(False)
    view.apply_dubbing.click()
    assert changes == [('a', False)]
    view.close()


def test_busy_review_shows_elapsed_and_keeps_cancel_available():
    app = QApplication.instance() or QApplication([])
    view = OverlayReviewView()
    view.begin_work('Đang xuất video 1/2: 10.mp4')
    assert view.progress.maximum() == 0
    assert view.timer.isActive()
    assert not view.render_button.isEnabled()
    assert view.cancel_button.isEnabled()
    cancelled = []
    view.cancel_requested.connect(lambda: cancelled.append(True))
    view.cancel_button.click()
    assert cancelled == [True]
    view._started -= 65
    view._tick()
    assert '01:05' in view.elapsed.text()
    view.end_work('Hoàn tất.')
    assert not view.timer.isActive()
    assert view.status.text() == 'Hoàn tất.'
    assert view.cancel_button.isHidden()
    view.close()
