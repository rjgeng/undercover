"""The policy wording and the claims manual, split into numbered sections."""

import re

from backend.models import Section

NAMES = {"wording": "policy wording", "manual": "claims manual"}
GIVEN = {"wording": [1, 9, 10, 11], "manual": [2, 3, 5, 6, 9]}  # every claim needs
HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)
NOTE = re.compile(r"^\*\*(.+?)\.\*\*", re.MULTILINE)


def split(document: str, text: str) -> list[Section]:
    """Split a document at its numbered headings, leaving out its introduction."""
    headings = list(HEADING.finditer(text))
    ends = [heading.start() for heading in headings[1:]] + [len(text)]
    return [
        Section(
            document=document,
            number=int(heading[1]),
            title=heading[2],
            text=text[heading.start() : end].strip(),
        )
        for heading, end in zip(headings, ends, strict=True)
    ]


def given(document: str, text: str) -> str:
    """Give the sections of a document that every claim needs, in full."""
    sections = [s for s in split(document, text) if s.number in GIVEN[document]]
    return "\n\n".join(
        [
            f"## Sections every claim needs, from the {NAMES[document]}",
            *(section.text.replace("## ", "### ", 1) for section in sections),
        ]
    )


def contents(document: str, text: str) -> str:
    """List a document's sections, and the notes in each, for the agent to look up."""
    lines = [f"## Contents of the {NAMES[document]}", ""]
    for section in split(document, text):
        line = f"{section.number}. {section.title}"
        notes = NOTE.findall(section.text)
        if section.number in GIVEN[document]:
            line += ", given above"
        elif notes:
            line += f": {', '.join(notes)}"
        lines.append(line)
    return "\n".join(lines)
