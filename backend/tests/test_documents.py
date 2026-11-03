import re

import pytest

from backend.database import DATA
from backend.documents import split


def test_read_a_manual_section(client):
    section = client.get("/api/documents/manual/sections/9").json()
    assert (section["document"], section["number"], section["title"]) == (
        "manual",
        9,
        "Repeat claims",
    )
    assert section["text"].startswith("## 9. Repeat claims\n")
    assert "third claim within any 12 month period" in section["text"]
    assert "## 10" not in section["text"]


def test_read_a_wording_section(client):
    section = client.get("/api/documents/wording/sections/10").json()
    assert section["title"] == "How we work out your payment"


@pytest.mark.parametrize(
    ("path", "detail"),
    [
        ("manual/sections/15", "Section 15 of the claims manual not found"),
        ("handbook/sections/1", "Document handbook not found"),
    ],
)
def test_unknown_sections(client, path, detail):
    response = client.get(f"/api/documents/{path}")
    assert response.status_code == 404
    assert response.json()["detail"] == detail


@pytest.mark.parametrize(
    ("document", "file", "count"),
    [("wording", "policy_wording.md", 12), ("manual", "claims_manual.md", 14)],
)
def test_the_sections_make_up_the_document(document, file, count):
    text = (DATA / file).read_text(encoding="utf-8")
    sections = split(document, text)
    assert [section.number for section in sections] == list(range(1, count + 1))
    body = text[text.index("\n## 1. ") :]
    assert "\n\n".join(section.text for section in sections) == body.strip()


def test_the_instructions_come_in_two_parts(client):
    instructions = client.get("/api/instructions").json()
    assert instructions["queue"].startswith("# UnderCover Agent: running the queue")
    assert instructions["claim"].startswith("# UnderCover Agent: working a claim")


def contents(claim, name):
    """Return the numbered lines of one document's contents."""
    block = claim.split(f"## Contents of the {name}\n")[1].split("\n## ")[0]
    return re.findall(r"^\d+\. .+$", block, re.MULTILINE)


def test_the_claim_instructions_end_with_the_contents(client):
    claim = client.get("/api/instructions").json()["claim"]
    wording = contents(claim, "policy wording")
    manual = contents(claim, "claims manual")
    assert (len(wording), wording[0], wording[-1]) == (
        12,
        "1. Your plan",
        "12. Definitions",
    )
    assert (len(manual), manual[-1]) == (14, "14. Records")
    notes = manual[6].removeprefix("7. Interpretation notes: ").split(", ")
    assert notes == [
        "Unattended belongings",
        "Vehicles",
        "Pairs and sets",
        "Wild animals",
        "Waiting periods",
        "Delay on the way home",
        "Reasonable accommodation",
        "Consequential losses",
        "The value of information",
        "Adventure sports",
        "Pre-existing conditions",
        "Treatment that can wait",
    ]


def test_the_instructions_hold_no_section_text(client):
    instructions = client.get("/api/instructions").json()
    claim = instructions["claim"]
    assert "Count back 60 days" not in claim
    assert "## 10. How we work out your payment" not in claim
    for text in instructions.values():
        assert "data/" not in text
