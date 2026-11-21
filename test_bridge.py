"""Offline tests for bridge_core: pairing, owner filter, dedup."""
import bridge_core as core


def upd(uid, chat_id, text):
    return {"update_id": uid, "message": {"chat": {"id": chat_id}, "text": text}}


def fresh_state(code="483920"):
    state = core.load_state("/nonexistent/state.json")
    core.set_pair_code(state, code)
    return state


def test_pairing_flow():
    s = fresh_state()
    # wrong code: ignored, still unpaired
    ev = core.process_updates(s, [upd(1, 111, "/pair 000000")])
    assert ev == [] and s["owner_chat_id"] is None
    # random text before pairing: ignored
    ev = core.process_updates(s, [upd(2, 111, "سلام")])
    assert ev == [] and s["owner_chat_id"] is None
    # correct code pairs and burns the code
    ev = core.process_updates(s, [upd(3, 111, "/pair 483920")])
    assert ev == [{"type": "paired", "chat_id": 111}]
    assert s["owner_chat_id"] == 111 and s["pair_code_hash"] is None


def test_owner_filter_and_dedup():
    s = fresh_state()
    core.process_updates(s, [upd(1, 111, "/pair 483920")])
    # owner's message passes
    ev = core.process_updates(s, [upd(2, 111, "یه خبر بده")])
    assert len(ev) == 1 and ev[0]["text"] == "یه خبر بده"
    # stranger's message ignored
    ev = core.process_updates(s, [upd(3, 999, "من غریبه‌ام")])
    assert ev == []
    # same update replayed: dedup by watermark
    ev = core.process_updates(s, [upd(2, 111, "یه خبر بده")])
    assert ev == []
    # non-message update advances nothing harmful
    ev = core.process_updates(s, [{"update_id": 4, "edited_message": {}}])
    assert ev == [] and s["last_update_id"] == 4


if __name__ == "__main__":
    test_pairing_flow()
    test_owner_filter_and_dedup()
    print("ALL TESTS PASSED")
