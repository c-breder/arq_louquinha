from works.sanitize import autoparagraph, clean_html


def test_removes_scripts_and_event_handlers():
    html = '<p onclick="alert(1)">oi</p><script>alert(2)</script><a href="javascript:alert(3)">x</a>'
    cleaned = clean_html(html)
    assert "script" not in cleaned
    assert "onclick" not in cleaned
    assert "javascript" not in cleaned
    assert "<p>oi</p>" in cleaned


def test_links_get_safe_rel():
    cleaned = clean_html('<a href="https://exemplo.com">site</a>')
    assert 'rel="nofollow noopener noreferrer ugc"' in cleaned


def test_images_only_when_allowed_and_only_from_own_media():
    own = '<img src="/media/imagens/1/abc.webp" alt="foto" width="10" height="10">'
    external = '<img src="https://rastreador.example/pixel.png">'
    assert "<img" not in clean_html(own)
    allowed = clean_html(own + external, allow_images=True)
    assert 'src="/media/imagens/1/abc.webp"' in allowed
    assert "rastreador" not in allowed


def test_image_size_must_be_numeric():
    cleaned = clean_html('<img src="/media/imagens/1/a.webp" width="100%">', allow_images=True)
    assert "width" not in cleaned


def test_autoparagraph_plain_text():
    assert autoparagraph("um\ndois\n\ntrês") == "<p>um<br>dois</p><p>três</p>"
    assert autoparagraph("<p>já tem</p>") == "<p>já tem</p>"
