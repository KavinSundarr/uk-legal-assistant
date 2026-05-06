from __future__ import annotations

from typing import Dict

# ---------------------------------------------------------------------------
# Base disclaimer (appended to every response)
# ---------------------------------------------------------------------------

_BASE = (
    "This information is provided for general guidance only and does not "
    "constitute legal advice. Laws and regulations change — always verify "
    "with official sources."
)

# ---------------------------------------------------------------------------
# Category-specific disclaimers
# ---------------------------------------------------------------------------

_DISCLAIMERS: Dict[str, str] = {
    "immigration": (
        "Immigration law is complex and highly individual. This information "
        "is for general guidance only and is not a substitute for advice from "
        "a regulated immigration adviser or solicitor. Rules change frequently "
        "— always check the latest guidance directly with UK Visas and "
        "Immigration (UKVI) at gov.uk/ukvi or call the UKVI helpline. "
        "Incorrect immigration applications can lead to refusal and affect "
        "future applications. Consult a solicitor regulated by the Solicitors "
        "Regulation Authority (SRA) or an OISC-registered adviser before "
        "taking any action."
    ),
    "student": (
        "Student visa rules are administered by UKVI and can change with "
        "little notice. Course and institution requirements, English language "
        "thresholds, and financial requirements must all be met simultaneously. "
        "Always verify current requirements at gov.uk/student-visa and with "
        "your university's international student advisory service. Seek "
        "independent immigration advice from an OISC-registered adviser or "
        "SRA-regulated solicitor for your specific situation."
    ),
    "driving": (
        "Road traffic law and DVLA rules are updated regularly. Penalties, "
        "point thresholds, and licence requirements stated here may have "
        "changed. Always verify current rules at gov.uk/dvla, the Highway "
        "Code, or by contacting the DVLA directly. For motoring offences or "
        "licence disputes consult a solicitor specialising in road traffic law."
    ),
    "employment": (
        "Employment law rights depend on your contract type, length of "
        "service, and individual circumstances. Statutory minimums change "
        "annually (e.g. National Living Wage, holiday entitlement). For "
        "disputes, free impartial advice is available from ACAS "
        "(acas.org.uk / 0300 123 1100) before considering an employment "
        "tribunal. Consult an employment solicitor or Citizens Advice for "
        "guidance specific to your situation."
    ),
    "housing": (
        "Housing and tenancy law differs between England, Wales, Scotland, "
        "and Northern Ireland. Eviction rules, deposit protection schemes, "
        "and rent increase procedures are jurisdiction-specific. For urgent "
        "housing issues contact Shelter (shelter.org.uk / 0808 800 4444) or "
        "your local council's housing department. Always take independent "
        "legal advice before signing tenancy agreements or responding to "
        "eviction notices."
    ),
    "healthcare": (
        "NHS entitlements and patient rights can depend on your residency "
        "status, immigration status, and the type of treatment required. "
        "Rules about overseas visitor charges are complex. Contact NHS "
        "England, your GP surgery, or the Patient Advice and Liaison Service "
        "(PALS) for guidance specific to your situation. For formal "
        "complaints or clinical negligence matters, consult a solicitor or "
        "the Parliamentary and Health Service Ombudsman."
    ),
    "benefits": (
        "Benefit entitlements are assessed individually and depend on "
        "personal circumstances including income, savings, household "
        "composition, and immigration status. Rates and eligibility criteria "
        "change each April. Use the official benefits calculator at "
        "gov.uk/benefits-calculators for an estimate. For complex situations "
        "or appeals, free specialist advice is available from Citizens Advice "
        "(citizensadvice.org.uk) or Turn2us (turn2us.org.uk)."
    ),
    "criminal": (
        "If you are under investigation or have been charged with a criminal "
        "offence you have the right to free and independent legal advice. "
        "Contact a duty solicitor immediately — do not answer police questions "
        "without legal representation. This information is general guidance "
        "only and cannot replace advice from a criminal defence solicitor. "
        "Find a solicitor via the Law Society at solicitors.lawsociety.org.uk "
        "or call the Defence Solicitor Call Centre on 0207 0205 999."
    ),
}

_GENERAL = (
    "This information is provided for general guidance only and does not "
    "constitute legal advice. Laws and regulations may have changed since "
    "this content was indexed. Always consult a qualified solicitor or legal "
    "professional before taking any action based on this information."
)

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_disclaimer(category: str | None = None) -> str:
    """
    Return the category-specific disclaimer if available, otherwise the
    general disclaimer.  *category* should match a key in LEGAL_CATEGORIES.
    """
    if category and category in _DISCLAIMERS:
        return _DISCLAIMERS[category] + "\n\n" + _BASE
    return _GENERAL


def get_seek_advice(category: str | None = None) -> str:
    """Short single-sentence call-to-action for the response footer."""
    _SEEK: Dict[str, str] = {
        "immigration": (
            "For immigration advice consult an OISC-registered adviser or "
            "SRA-regulated solicitor, and verify with UKVI at gov.uk/ukvi."
        ),
        "student": (
            "Contact your university's international student office and verify "
            "current requirements at gov.uk/student-visa."
        ),
        "driving": (
            "Verify current rules with the DVLA at gov.uk/dvla or consult a "
            "road traffic solicitor."
        ),
        "employment": (
            "Contact ACAS (acas.org.uk) or a qualified employment solicitor "
            "before taking formal action."
        ),
        "housing": (
            "Contact Shelter (shelter.org.uk) or a housing solicitor for "
            "advice specific to your tenancy and jurisdiction."
        ),
        "healthcare": (
            "Speak to PALS at your NHS Trust or consult a solicitor for "
            "complaints and formal disputes."
        ),
        "benefits": (
            "Get a personalised benefits check from Citizens Advice "
            "(citizensadvice.org.uk) or Turn2us (turn2us.org.uk)."
        ),
        "criminal": (
            "Always seek independent legal advice from a criminal defence "
            "solicitor before responding to police or court proceedings."
        ),
    }
    return _SEEK.get(
        category or "",
        "Always consult a qualified solicitor or legal professional before "
        "taking any action based on this information.",
    )
