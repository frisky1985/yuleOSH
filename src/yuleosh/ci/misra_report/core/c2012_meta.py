#!/usr/bin/env python3
"""MISRA C:2012 → C:2023 semantic mapping (platform honesty layer).

cppcheck's misra addon (through 2.17.x, and current main) ONLY implements
MISRA C:2012 checks. yuleOSH's rule set (misra-rules.yaml) is C:2023.
For rules whose C:2023 text is *unchanged* from C:2012, mapping a C:2012
violation to the C:2023 rule ID is safe (same semantics). For rules whose
C:2023 text was *modified* (13 rules), the two standards describe DIFFERENT
requirements — reporting a C:2012 finding under the C:2023 ID would mislabel
it. This module supplies the C:2012 severity/title for those rules so the
report layer can label them honestly.

Source of truth: MISRA C:2012 standard rule texts (public summary).
"""

# 13 rules whose C:2012 → C:2023 text changed. Values are the C:2012
# severity + short title, used when a violation carries a c2012 rule ID.
C2012_MODIFIED_RULES: dict[str, dict] = {
    "Rule-1.1": {
        "severity": "required",
        "title": "The program shall contain no undefined behavior",
    },
    "Rule-2.2": {
        "severity": "required",
        "title": "There shall be no dead code",
    },
    "Rule-8.13": {
        "severity": "advisory",
        "title": "A pointer shall point to a const-qualified type whenever possible",
    },
    "Rule-10.1": {
        "severity": "required",
        "title": "Operands shall not be of inappropriate essential type",
    },
    "Rule-10.3": {
        "severity": "required",
        "title": "The value of an expression shall not be assigned to an object with a narrower essential type",
    },
    "Rule-10.4": {
        "severity": "required",
        "title": "Both operands of an operator in which the usual arithmetic conversions are performed shall have the same essential type category",
    },
    "Rule-11.3": {
        "severity": "required",
        "title": "A cast shall not be performed between a pointer to object type and a pointer to a different object type",
    },
    "Rule-16.6": {
        "severity": "required",
        "title": "Every switch statement shall have a default label, and it shall be the last label in the switch",
    },
    "Rule-17.2": {
        "severity": "advisory",
        "title": "Functions shall not call themselves, either directly or indirectly",
    },
    "Rule-18.4": {
        "severity": "required",
        "title": "The +, -, += and -= operators shall not be applied to an expression of pointer type",
    },
    "Rule-18.5": {
        "severity": "required",
        "title": "Declarations should contain no more than two levels of pointer nesting",
    },
    "Rule-21.12": {
        "severity": "advisory",
        "title": "The standard header file <time.h> shall not be used",
    },
    "Rule-22.1": {
        "severity": "required",
        "title": "All resources obtained dynamically by means of Standard Library functions shall be released",
    },
}

# Short numeric form lookup ("10.4" -> C:2012 data) for parser use.
_C2012_SHORT: dict[str, dict] = {}
for _rid, _info in C2012_MODIFIED_RULES.items():
    _num = _rid.split("-", 1)[1]  # "Rule-10.4" -> "10.4"
    _C2012_SHORT[_num] = _info


def c2012_info(rule_id: str) -> dict | None:
    """Return C:2012 severity/title for a rule ID if it is a modified rule.

    Accepts ``misra-c2012-10.4``, ``10.4``, ``Rule-10.4``.
    Returns None for unchanged rules (C:2012 == C:2023 semantics, no special
    labeling needed).
    """
    if not rule_id:
        return None
    rid = rule_id.strip().lower()
    # misra-c2012-10.4 -> 10.4
    if rid.startswith("misra-c2012-"):
        num = rid[len("misra-c2012-"):]
    # rule-10.4 / rule 10.4
    elif rid.startswith("rule"):
        num = rid.replace("rule", "", 1).strip().lstrip("- ").strip()
    else:
        num = rid
    if num in _C2012_SHORT:
        return dict(_C2012_SHORT[num])
    return None
