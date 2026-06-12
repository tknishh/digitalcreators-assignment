from app.services.clip_analyzer import ClipAnalyzer, FrameCandidate


def test_select_clips_with_prompt_orders_by_score():
    analyzer = ClipAnalyzer()
    candidates = [
        FrameCandidate("a", "jobs/1/a.mp4", "a.mp4", 2.0, 0.2),
        FrameCandidate("b", "jobs/1/b.mp4", "b.mp4", 4.0, 0.9),
        FrameCandidate("c", "jobs/1/c.mp4", "c.mp4", 6.0, 0.5),
    ]
    selected = analyzer.select_clips(candidates, target_duration_sec=12.0, prompt="product launch")
    assert selected
    assert selected[0]["storage_key"] == "jobs/1/b.mp4"
    assert sum(c["duration_sec"] for c in selected) >= 10


def test_select_clips_without_prompt_rotates_videos():
    analyzer = ClipAnalyzer()
    candidates = [
        FrameCandidate("a", "jobs/1/a.mp4", "a.mp4", 2.0, 0.2),
        FrameCandidate("a2", "jobs/1/a.mp4", "a.mp4", 6.0, 0.3),
        FrameCandidate("b", "jobs/1/b.mp4", "b.mp4", 4.0, 0.9),
    ]
    selected = analyzer.select_clips(candidates, target_duration_sec=12.0, prompt=None)
    keys = [c["storage_key"] for c in selected]
    assert "jobs/1/a.mp4" in keys
    assert "jobs/1/b.mp4" in keys
