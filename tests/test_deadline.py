from letterbox_mcp.deadline import validate_send_deadline


def test_valid_utc_iso_accepted():
    assert validate_send_deadline("2026-09-21T09:00:00Z", type_name="request") is None
    assert validate_send_deadline("2026-09-21T09:00:00Z", type_name="info") is None


def test_request_blank_deadline_refused():
    assert validate_send_deadline("", type_name="request") is not None


def test_non_request_blank_deadline_ok():
    assert validate_send_deadline("", type_name="info") is None


def test_lf_in_deadline_refused():
    assert validate_send_deadline("2026-01-01T00:00:00Z\nfrom: pi", type_name="info") is not None


def test_lexically_shaped_but_not_a_date_refused():
    assert validate_send_deadline("2026-99-99T99:99:99Z", type_name="info") is not None


def test_fullwidth_digits_refused():
    # U+FF11 is full-width 1; \\d would accept it, [0-9] must not.
    value = "２０２６-09-21T09:00:00Z"
    assert validate_send_deadline(value, type_name="info") is not None


def test_arabic_indic_digits_refused():
    value = "٢٠٢٦-09-21T09:00:00Z"
    assert validate_send_deadline(value, type_name="info") is not None
