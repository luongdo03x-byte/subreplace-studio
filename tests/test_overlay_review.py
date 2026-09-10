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
