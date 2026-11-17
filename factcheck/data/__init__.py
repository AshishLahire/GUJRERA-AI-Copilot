"""Dataset loaders and schemas for the Fujitsu misinformation benchmark."""

from factcheck.data.loaders import (
    ClaimRecord,
    FakeNotice,
    IssuerEntry,
    IssuerRegistry,
    MultilingualClaimsBundle,
    NarrativeRecord,
    OfficialDoc,
    SyntheticForgery,
    WhatsAppVariant,
    load_fake_notices,
    load_issuer_registry,
    load_multilingual_claims,
    load_official_docs,
    load_synthetic_forgeries,
    load_whatsapp_variants,
)

__all__ = [
    "ClaimRecord",
    "FakeNotice",
    "IssuerEntry",
    "IssuerRegistry",
    "MultilingualClaimsBundle",
    "NarrativeRecord",
    "OfficialDoc",
    "SyntheticForgery",
    "WhatsAppVariant",
    "load_fake_notices",
    "load_issuer_registry",
    "load_multilingual_claims",
    "load_official_docs",
    "load_synthetic_forgeries",
    "load_whatsapp_variants",
]
