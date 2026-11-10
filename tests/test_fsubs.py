from link_sharing_bot.fsubs import _panel_markup, _gate_markup


def test_fsubs_panel_has_all_requested_actions():
    markup = _panel_markup()
    actions = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
    }
    assert {"fsubs:add", "fsubs:remove", "fsubs:edit", "fsubs:back", "fsubs:close"} <= actions


def test_fsubs_user_prompt_has_join_check_and_close():
    markup = _gate_markup([(-1001234567890, "Example Channel", "https://t.me/example")])
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert any(button.url == "https://t.me/example" for button in buttons)
    assert any(button.callback_data == "fsubs:check" for button in buttons)
    assert any(button.callback_data == "branding:close" for button in buttons)
