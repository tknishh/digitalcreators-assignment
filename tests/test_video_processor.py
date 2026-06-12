from app.services.video_processor import pick_transition_style


def test_pick_transition_style_cycles():
    styles = "fade,smoothleft,dissolve"
    from app.config import settings

    original = settings.transition_styles
    settings.transition_styles = styles
    try:
        assert pick_transition_style(1) == "fade"
        assert pick_transition_style(2) == "smoothleft"
        assert pick_transition_style(3) == "dissolve"
        assert pick_transition_style(4) == "fade"
    finally:
        settings.transition_styles = original
