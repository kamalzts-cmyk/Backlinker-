"""Email verification -- deterministic layers only. See PRODUCT_SPEC.md
§4.6/§13's layered model: syntax -> domain DNS -> MX -> SMTP.

We implement syntax, DNS, MX, and a disposable-domain check. We do NOT
implement SMTP-level mailbox/catch-all probing (an RCPT TO handshake
against the real mail server): it needs outbound port 25, which is
blocked in this project's build sandbox (confirmed by a direct TCP
connect attempt timing out), and PRODUCT_SPEC.md is independently
skeptical of it anyway -- catch-all domains accept almost any address, so
a "successful" SMTP probe is not proof of a real mailbox. Most
importantly: **we never send an email to verify one**, per
PRODUCT_SPEC.md §13 ("SMTP verification is not universally reliable...
we should not send test emails just to verify addresses").

Given those two layers are unreachable/undesirable, the strongest
signal we can produce is LIKELY (valid syntax + the domain actually has
mail exchangers) -- never VERIFIED, and CATCH_ALL is modeled but never
set by this module. A future deployment with SMTP egress could add that
layer behind the same EmailVerificationLayer.SMTP enum value without
changing anything else here.
"""

import re
from dataclasses import dataclass

import dns.exception
import dns.resolver

from app.db.models import (
    Contact,
    ContactVerificationStatus,
    EmailVerification,
    EmailVerificationLayer,
)
from app.engines.contact.classify import is_role_address

_EMAIL_SYNTAX_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# A small, well-known set of disposable/temporary-inbox providers.
# Deterministic and easy to extend; not exhaustive.
_DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "temp-mail.org",
        "throwawaymail.com",
        "yopmail.com",
        "trashmail.com",
        "getnada.com",
        "fakeinbox.com",
        "sharklasers.com",
        "maildrop.cc",
    }
)

_DNS_TIMEOUT_SECONDS = 5.0


@dataclass
class EmailVerificationResult:
    email: str
    layer_reached: EmailVerificationLayer
    syntax_valid: bool
    domain_has_mx: bool | None  # None = DNS lookup itself failed (unknown, not "confirmed absent")
    is_disposable_domain: bool
    is_role_address: bool
    status: ContactVerificationStatus


def check_syntax(email: str) -> bool:
    return bool(_EMAIL_SYNTAX_RE.match(email))


def check_mx(domain: str) -> bool | None:
    """True if the domain has mail exchangers (directly via MX, or via
    the RFC 5321 fallback of accepting mail at its A/AAAA record when no
    MX is published). False if DNS positively says neither exists. None
    if the lookup itself failed (timeout, no resolver reachable) --
    distinct from a confirmed-absent domain.
    """
    resolver = dns.resolver.Resolver()
    resolver.timeout = _DNS_TIMEOUT_SECONDS
    resolver.lifetime = _DNS_TIMEOUT_SECONDS

    try:
        answers = resolver.resolve(domain, "MX")
        return len(answers) > 0
    except dns.resolver.NXDOMAIN:
        return False
    except dns.resolver.NoAnswer:
        pass  # no MX record -- fall through to the A/AAAA fallback check
    except dns.exception.DNSException:
        return None

    try:
        resolver.resolve(domain, "A")
        return True
    except dns.resolver.NXDOMAIN:
        return False
    except dns.exception.DNSException:
        return None


def verify_email_address(email: str) -> EmailVerificationResult:
    syntax_valid = check_syntax(email)
    if not syntax_valid:
        return EmailVerificationResult(
            email=email,
            layer_reached=EmailVerificationLayer.SYNTAX,
            syntax_valid=False,
            domain_has_mx=None,
            is_disposable_domain=False,
            is_role_address=False,
            status=ContactVerificationStatus.INVALID,
        )

    domain = email.split("@", 1)[1].lower()
    disposable = domain in _DISPOSABLE_DOMAINS
    role = is_role_address(email)
    mx = check_mx(domain)

    if disposable or mx is False:
        status = ContactVerificationStatus.INVALID
    elif mx is None:
        status = ContactVerificationStatus.UNKNOWN
    elif role:
        status = ContactVerificationStatus.ROLE_ADDRESS
    else:
        status = ContactVerificationStatus.LIKELY

    return EmailVerificationResult(
        email=email,
        layer_reached=EmailVerificationLayer.MX,
        syntax_valid=True,
        domain_has_mx=mx,
        is_disposable_domain=disposable,
        is_role_address=role,
        status=status,
    )


def verify_contact_email(session, contact: Contact) -> EmailVerification | None:
    """Runs verification for a Contact's email, updates the contact's
    own verification_status/confidence_score, and records a historical
    EmailVerification row. Returns None if the contact has no email.
    """
    if contact.email is None:
        return None

    result = verify_email_address(contact.email)
    contact.verification_status = result.status
    contact.confidence_score = _confidence_for_result(result)

    record = EmailVerification(
        contact_id=contact.id,
        layer_reached=result.layer_reached,
        is_disposable_domain=result.is_disposable_domain,
        result_status=result.status,
    )
    session.add(record)
    session.flush()
    return record


def _confidence_for_result(result: EmailVerificationResult) -> int:
    if result.status == ContactVerificationStatus.INVALID:
        return 0
    if result.status == ContactVerificationStatus.UNKNOWN:
        return 30
    if result.status == ContactVerificationStatus.ROLE_ADDRESS:
        return 75
    if result.status == ContactVerificationStatus.LIKELY:
        return 80
    return 50
