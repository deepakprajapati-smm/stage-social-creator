"""
workers/naming_engine.py — Hindi/English title → social media handles

Converts movie/series titles to valid handles for:
  - Instagram  (stage.titlename, max 30 chars, a-z 0-9 _ .)
  - Facebook   (StageTitleName, max 50 chars, alphanumeric + .)
  - YouTube    (@StageTitleName, max 30 chars, alphanumeric + _ - .)

Supports Hindi Devanagari input via indic-transliteration library.
Install: pip install indic-transliteration
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional


# ── Canonical overrides for known district names ───────────────────────────
# Use official English spellings directly (no transliteration needed)
DISTRICT_CANONICAL: dict[str, str] = {
    "banswara":    "Banswara",
    "dungarpur":   "Dungarpur",
    "pratapgarh":  "Pratapgarh",
    "udaipur":     "Udaipur",
    "rajsamand":   "Rajsamand",
    "salumbar":    "Salumbar",
    "kota":        "Kota",
    "bundi":       "Bundi",
    "baran":       "Baran",
    "jhalawar":    "Jhalawar",
    "chittorgarh": "Chittorgarh",
    "bhilwara":    "Bhilwara",
}


@dataclass
class SocialHandles:
    """All platform handles generated for a title."""
    input_title:   str
    roman_form:    str        # clean Roman transliteration
    slug:          str        # kebab-case for URLs/filenames

    ig_handle:     str        # stage.titlename
    fb_page_name:  str        # display name: "STAGE Title Name"
    fb_username:   str        # vanity URL: StageTitleName
    yt_channel_name: str      # display name (Devanagari if Hindi)
    yt_handle:     str        # @StageTitleName (without @)

    def as_dict(self) -> dict:
        return {
            "input_title":      self.input_title,
            "roman_form":       self.roman_form,
            "slug":             self.slug,
            "instagram": {
                "handle":       f"@{self.ig_handle}",
                "handle_raw":   self.ig_handle,
            },
            "facebook": {
                "page_name":    self.fb_page_name,
                "username":     self.fb_username,
                "url":          f"https://facebook.com/{self.fb_username}",
            },
            "youtube": {
                "channel_name": self.yt_channel_name,
                "handle":       f"@{self.yt_handle}",
                "handle_raw":   self.yt_handle,
            },
        }


# ── Devanagari detection ───────────────────────────────────────────────────

def _has_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097F" for ch in text)


# ── Transliteration ────────────────────────────────────────────────────────

def _transliterate(text: str) -> str:
    """
    Devanagari → clean Roman ASCII suitable for social handles.
    Uses Harvard-Kyoto (HK) scheme which produces pure ASCII output.
    Falls back to Unicode normalization if library not installed.
    """
    try:
        from indic_transliteration import sanscript
        from indic_transliteration.sanscript import transliterate

        text = unicodedata.normalize("NFC", text)
        hk = transliterate(text, sanscript.DEVANAGARI, sanscript.HK)

        # HK → readable ASCII:
        # Long vowels: A→a, I→i, U→u
        # Anusvara M → n, Visarga H → drop
        for src, dst in [("A", "a"), ("I", "i"), ("U", "u"), ("M", "n"), ("H", "")]:
            hk = hk.replace(src, dst)

        hk = hk.lower()
        hk = hk.encode("ascii", errors="ignore").decode("ascii")
        hk = re.sub(r"\s+", " ", hk).strip()
        return hk

    except ImportError:
        # Fallback: Unicode NFKD strip
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", errors="ignore").decode("ascii")
        return text.lower().strip()


def _to_roman(title: str) -> str:
    """Convert title (Hindi or English) to clean Roman form."""
    # Check if it matches a canonical district name first
    lower = title.lower().strip()
    if lower in DISTRICT_CANONICAL:
        return DISTRICT_CANONICAL[lower].lower()

    if _has_devanagari(title):
        return _transliterate(title)

    return title.lower()


# ── Slug ────────────────────────────────────────────────────────────────────

def to_slug(title: str, separator: str = "-") -> str:
    """'बांसवाड़ा की कहानी' → 'banswada-ki-kahani'"""
    roman = _to_roman(title)
    slug = re.sub(r"[^a-z0-9]+", separator, roman)
    return slug.strip(separator)


# ── Instagram handle ────────────────────────────────────────────────────────
# Rules: a-z 0-9 _ .  |  max 30 chars  |  no consecutive dots, no dot at start/end

def _clean_ig(text: str) -> str:
    return re.sub(r"[^a-z0-9_.]", "", text.lower())

def _ig_safe(handle: str) -> str:
    handle = re.sub(r"\.{2,}", ".", handle)
    return handle.strip(".")[:30]

def generate_ig_handle(title: str, prefix: str = "stage") -> str:
    """'Banswara' → 'stage.banswara'"""
    roman = _to_roman(title)
    words = re.split(r"[^a-z0-9]+", roman)
    core  = "".join(w for w in words if w)
    core  = _clean_ig(core)
    prefix = _clean_ig(prefix)
    handle = f"{prefix}.{core}" if prefix else core
    return _ig_safe(handle)


# ── Facebook username ────────────────────────────────────────────────────────
# Rules: a-z A-Z 0-9 .  |  max 50 chars  |  min 5 chars

def _clean_fb(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9.]", "", text)

def generate_fb_username(title: str, prefix: str = "Stage") -> str:
    """'Banswara Ki Kahani' → 'StageBanswadaKiKahani'"""
    roman = _to_roman(title)
    words = re.split(r"[^a-z0-9]+", roman)
    core  = "".join(w.capitalize() for w in words if w)
    username = _clean_fb(f"{prefix}{core}")
    username = username[:50]
    if len(username) < 5:
        username += "Official"
    return username

def generate_fb_page_name(title: str, prefix: str = "STAGE") -> str:
    """Returns display name. Keeps Devanagari if Hindi input."""
    if _has_devanagari(title):
        return f"{prefix} {title}"[:75]
    return f"{prefix} {title.title()}"[:75]


# ── YouTube ──────────────────────────────────────────────────────────────────
# Handle rules: a-z A-Z 0-9 _ - .  |  max 30 chars  |  min 3 chars

def _clean_yt_handle(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_.\-]", "", text)
    text = re.sub(r"\.{2,}", ".", text)
    return text.strip(".-")

def generate_yt_handle(title: str, prefix: str = "Stage") -> str:
    """'Banswara' → 'StagebanSwara' → sanitized to '@StageBanswara'"""
    roman = _to_roman(title)
    words = re.split(r"[^a-z0-9]+", roman)
    core  = "".join(w.capitalize() for w in words if w)
    handle = _clean_yt_handle(f"{prefix}{core}")
    handle = handle[:30]
    if len(handle) < 3:
        handle += "Official"
    return handle

def generate_yt_channel_name(title: str, prefix: str = "STAGE") -> str:
    """Returns display name — keeps Devanagari for regional SEO."""
    if _has_devanagari(title):
        return f"{prefix} {title}"[:100]
    return f"{prefix} {title.title()}"[:100]


# ── Main entry point ─────────────────────────────────────────────────────────

def generate_handles(title: str, brand_prefix: str = "STAGE") -> SocialHandles:
    """
    Generate all social media handles for a given title.

    Args:
        title:        Hindi ("बांसवाड़ा") or English ("Banswara Ki Kahani")
        brand_prefix: Brand name (default "STAGE")

    Returns:
        SocialHandles dataclass with all platform handles.

    Examples:
        generate_handles("Banswara")
        generate_handles("बांसवाड़ा की कहानी")
        generate_handles("Kota Ke Kisse")
    """
    prefix_title = brand_prefix.title()   # "Stage"
    prefix_upper = brand_prefix.upper()   # "STAGE"
    prefix_lower = brand_prefix.lower()   # "stage"

    roman = _to_roman(title)
    slug  = to_slug(title)

    return SocialHandles(
        input_title     = title,
        roman_form      = roman,
        slug            = slug,
        ig_handle       = generate_ig_handle(title, prefix=prefix_lower),
        fb_page_name    = generate_fb_page_name(title, prefix=prefix_upper),
        fb_username     = generate_fb_username(title, prefix=prefix_title),
        yt_channel_name = generate_yt_channel_name(title, prefix=prefix_upper),
        yt_handle       = generate_yt_handle(title, prefix=prefix_title),
    )


# ── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    test_titles = [
        "Banswara",
        "बांसवाड़ा",
        "बांसवाड़ा की कहानी",
        "Kota Ke Kisse",
        "Udaipur",
        "Chittorgarh",
    ]
    for t in test_titles:
        h = generate_handles(t)
        print(f"\n{'─'*50}")
        print(f"Input:   {t}")
        print(json.dumps(h.as_dict(), ensure_ascii=False, indent=2))
