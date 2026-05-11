from qa_agent.context.chunking import chunk


def test_short_text_returned_whole():
    assert chunk("hi", 100) == ["hi"]


def test_paragraph_split():
    text = "a" * 50 + "\n\n" + "b" * 50
    out = chunk(text, 60)
    assert all(len(c) <= 60 for c in out)
    assert len(out) >= 1


def test_long_sentence_hard_cut():
    out = chunk("x" * 250, 100)
    assert all(len(c) <= 100 for c in out)
    assert sum(len(c) for c in out) == 250
