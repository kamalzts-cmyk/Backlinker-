"""Real DNS lookups, no mocking -- unlike the Common Crawl connector,
plain DNS resolution works fine from this build sandbox (confirmed:
outbound HTTPS is proxied/restricted, but UDP/TCP DNS is not), so this
is genuinely proven against the live internet rather than fixtures.
"""

from app.db.models import ContactVerificationStatus
from app.engines.contact.verify_email import check_mx, check_syntax, verify_email_address


def test_check_syntax_valid():
    assert check_syntax("jane.doe@example.com") is True


def test_check_syntax_invalid():
    assert check_syntax("not-an-email") is False
    assert check_syntax("missing-domain@") is False
    assert check_syntax("@missing-local.com") is False


def test_check_mx_for_a_real_domain_with_mx_records():
    # gmail.com unquestionably has MX records
    assert check_mx("gmail.com") is True


def test_check_mx_for_a_domain_that_does_not_exist():
    assert check_mx("this-domain-almost-certainly-does-not-exist-abc123xyz.com") is False


def test_verify_email_address_valid_personal_address():
    result = verify_email_address("someone@gmail.com")
    assert result.syntax_valid is True
    assert result.domain_has_mx is True
    assert result.is_disposable_domain is False
    assert result.status == ContactVerificationStatus.LIKELY


def test_verify_email_address_role_address():
    result = verify_email_address("info@gmail.com")
    assert result.is_role_address is True
    assert result.status == ContactVerificationStatus.ROLE_ADDRESS


def test_verify_email_address_invalid_syntax():
    result = verify_email_address("not-an-email")
    assert result.status == ContactVerificationStatus.INVALID
    assert result.domain_has_mx is None  # never got far enough to check


def test_verify_email_address_nonexistent_domain():
    result = verify_email_address("someone@this-domain-almost-certainly-does-not-exist-abc123xyz.com")
    assert result.domain_has_mx is False
    assert result.status == ContactVerificationStatus.INVALID


def test_verify_email_address_disposable_domain():
    result = verify_email_address("throwaway@mailinator.com")
    assert result.is_disposable_domain is True
    assert result.status == ContactVerificationStatus.INVALID
