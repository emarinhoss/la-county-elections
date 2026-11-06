"""A one-sentence title for a ballot measure, taken from the county's own words (never written by us).

The county's measure text comes in two shapes:
  1. It opens with a headline: "AUTHORIZES BONDS FOR HOUSING AFFORDABILITY PROGRAMS. LEGISLATIVE STATUTE. Authorizes $11.25 billion ...",
     "Data Centers Prohibited. Shall an ordinance ...", "MEASURE ES: Shall a measure imposing ...".
  2. It opens straight with the ballot question: "Shall the measure permitting the City of Bell Gardens to sell ...".
The title is the headline when there is one (with the measure-type labels such as "LEGISLATIVE STATUTE" or "CHARTER AMENDMENT EE" and
a leading "MEASURE X:" removed), otherwise the first sentence of the ballot question. All-capitals text is converted to Title Case.
Anything longer than MAX characters is cut at a word boundary and ends with "...", the full text stays under "Read the measure".
"""
import re

MAX = 190
SMALL = {"of", "the", "and", "for", "to", "in", "or", "a", "an", "on", "by", "at", "from", "with", "that", "as", "than"}
ACRONYMS = {"LA", "US", "USA", "HVAC", "CEQA", "DUI", "II", "III", "IV", "VII", "EV", "ID", "DA", "COVID"}
# a sentence that is only a measure-type label: "LEGISLATIVE STATUTE", "INITIATIVE CONSTITUTIONAL AMENDMENT AND STATUTE", "CHARTER AMENDMENT EE", "PROPOSITION TE"
_KIND = r"(?:CONSTITUTIONAL AMENDMENT|CHARTER AMENDMENT|STATUTE|ORDINANCE|PROPOSITION)"
LABEL = re.compile(rf"(?:PROPOSED\s+)?(?:(?:COUNTY|CITY)\s+)?(?:(?:INITIATIVE|LEGISLATIVE)\s+)?{_KIND}(?:\s+AND\s+{_KIND})?(?:\s+[A-Z]{{1,4}})?")
QUESTION_START = re.compile(r"^(Shall|Should|To|With|Without|Does|Do)\b")


def _is_caps(s):
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 3 and all(c.isupper() for c in letters)


def _title_case(s):
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        core = re.sub(r"[^a-z]", "", w)
        if core.upper() in ACRONYMS:
            out.append(w.upper())
        elif i > 0 and core in SMALL:
            out.append(w)
        else:
            out.append("".join(seg[:1].upper() + seg[1:] if seg[:1].isalpha() else seg for seg in re.split(r"([-/])", w)))
    return " ".join(out)


def _sentences(text):
    """Split at '. ' / '? ' / '! ' followed by a capital or digit; keeps the text of each sentence without its final period."""
    parts = re.split(r"(?<!U\.S\.)(?<!\bNo\.)(?<!\bSt\.)(?<!\bDr\.)(?<!\bMr\.)(?<!\bMrs\.)(?<=[.?!])\s+(?=[A-Z0-9$\"“])", text)
    return [p.strip() for p in parts if p.strip()]


def _soften_caps(s):
    """If the sentence opens with ALL-CAPS emphasis ("WITHOUT INCREASING TAX RATES, to upgrade ..."), write that part in sentence case."""
    words = s.split()
    run = 0
    while run < len(words) and _is_caps(words[run].rstrip(",;:")):
        run += 1
    if run < 2 or run == len(words):
        return s
    head = " ".join(words[:run]).lower()
    return " ".join([head[:1].upper() + head[1:]] + words[run:])


def _cut(s):
    s = s.strip().rstrip(".:;, ")
    if len(s) <= MAX:
        return s
    return s[:MAX].rsplit(" ", 1)[0].rstrip(",;:- ") + "..."


def measure_title(text):
    """The one-sentence title for a measure's text, or None when there is no text."""
    t = " ".join((text or "").split())
    if not t:
        return None
    # "HEADLINE MEASURE C: To maintain ..." / "MEASURE ES: Shall ..." / "Measure YV. Shall ..."
    m = re.match(r"^(.*?)\s*\bMEASURE\s+[A-Z]{1,4}\s*[:.]\s*(.*)$", t, flags=re.I)
    if m and len(m.group(1)) < 120 and m.group(2):
        head, t = m.group(1).strip(" :."), m.group(2)
        head = re.sub(r"\bMEASURE$", "", head, flags=re.I).strip(" :.")
        if len(head.split()) >= 2 and not LABEL.fullmatch(head.upper()):
            return _cut(_title_case(head) if _is_caps(head) else head)
    # a leading run of ALL-CAPS words, possibly running straight into the question ("... DISPUTES Shall the measure ...")
    words = t.split()
    run = 0
    while run < len(words) and (_is_caps(words[run]) or not any(c.isalpha() for c in words[run]) or words[run] in {"A", "I", "OF", "TO", "OR", "AND", "IN", "ON", "BY", "AT", "ITS", "ITS'", "&"}):
        run += 1
    if run >= 3 and not words[run - 1].endswith(","):      # "WITHOUT INCREASING TAX RATES, to upgrade ..." is emphasis, not a headline
        caps = " ".join(words[:run])
        for sent in re.split(r"(?<=\.)\s+", caps):
            clean = sent.strip(" .")
            if clean and not LABEL.fullmatch(clean.upper()) and not re.fullmatch(r"MEASURE [A-Z]{1,4}", clean):
                return _cut(_title_case(clean))
    # a short mixed-case headline followed by the question ("Data Centers Prohibited. Shall an ordinance ...")
    sents = _sentences(t)
    if len(sents) > 1 and len(sents[0].split()) <= 14 and not QUESTION_START.match(sents[0]) and not sents[0].endswith("?"):
        return _cut(sents[0])
    if sents:
        first = sents[0]
        m = re.match(r"^(?P<head>[A-Z][^.?!;]{8,150}?)[:\s]\s*(?=(?:Shall|To|Without|With funds)\b)", first)
        if m and not QUESTION_START.match(first):
            head = m.group("head").strip(" :")
            hw = head.split()
            capped = sum(1 for w in hw if w[:1].isupper() or w.lower().strip(",") in SMALL or not w[:1].isalpha())
            if 3 <= len(hw) <= 16 and capped / len(hw) >= 0.7:     # "Good Government Cannabis Reform Measure To fund ..."
                return _cut(head)
        return _cut(_soften_caps(first))
    return None
