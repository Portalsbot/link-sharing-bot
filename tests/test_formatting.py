from link_sharing_bot.formatting import render_text

def test_small_caps_and_quote():
    output = render_text("(Q)Hello(/Q)", small_caps=True)
    assert "<blockquote>" in output and "</blockquote>" in output
    assert "ʜᴇʟʟᴏ" in output

def test_code_is_not_small_caps():
    output = render_text("(CODE)Hello(/CODE)", small_caps=True)
    assert "Hello" in output

def test_unsafe_link_is_not_rendered_as_anchor():
    output = render_text('(LINK url="javascript:alert(1)")click(/LINK)')
    assert '<a href=' not in output
