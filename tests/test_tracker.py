from vial_persistent_tracker import CentroidTracker, color_for_id


def test_new_detections_register_new_ids():
    tracker = CentroidTracker()
    objects = tracker.update([(10, 10, 5), (50, 50, 6)])
    assert set(objects.keys()) == {0, 1}


def test_id_persists_across_small_movement():
    tracker = CentroidTracker(max_distance=40)
    tracker.update([(10, 10, 5)])
    objects = tracker.update([(14, 12, 5)])
    assert list(objects.keys()) == [0]
    assert objects[0] == (14, 12, 5)


def test_track_is_dropped_after_max_disappeared():
    tracker = CentroidTracker(max_disappeared=2)
    tracker.update([(10, 10, 5)])
    objects = {}
    for _ in range(3):
        objects = tracker.update([])
    assert objects == {}


def test_far_detection_becomes_new_track_not_a_match():
    tracker = CentroidTracker(max_distance=20)
    tracker.update([(10, 10, 5)])
    objects = tracker.update([(500, 500, 5)])
    assert set(objects.keys()) == {0, 1}


def test_color_for_id_is_deterministic():
    assert color_for_id(3) == color_for_id(3)
    assert color_for_id(3) != color_for_id(4)
