"""The shapes of UnderCover's records in the API."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

Status = Literal["waiting", "in_progress", "waiting_for_sign_off", "decided"]
Decision = Literal["approve", "decline", "refer"]
Money = Annotated[float, Field(ge=0), AfterValidator(lambda amount: round(amount, 2))]


class Item(BaseModel):
    description: str
    category: str
    amount: float


class Document(BaseModel):
    name: str
    type: str
    content: str


class ClaimSummary(BaseModel):
    claim_id: str
    customer_name: str
    claim_type: str
    summary: str
    amount_claimed: float
    submitted_on: str
    status: Status
    decision: Decision | None
    payout: float | None


class Claim(BaseModel):
    claim_id: str
    policy_id: str
    customer_id: str
    claim_type: str
    submitted_on: str
    incident_date: str
    incident_location: str
    summary: str
    story: str
    items: list[Item]
    amount_claimed: float
    documents: list[Document]
    status: Status
    thread_id: str | None
    decision: Decision | None
    payout: float | None
    reasons: str | None
    policy_section: str | None
    decided_at: str | None
    signed_off_by: str | None
    signed_off_at: str | None
    paid_amount: float | None
    paid_at: str | None


class Trip(BaseModel):
    destination: str
    departs_on: str
    returns_on: str
    trip_cost: float


class Policy(BaseModel):
    policy_id: str
    customer_id: str
    plan: str
    add_ons: list[str]
    purchased_on: str
    sold_through: str
    trip: Trip
    travelers: list[str]
    status: str


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip: str


class PreviousClaim(BaseModel):
    claim_id: str
    filed_on: str
    incident_date: str
    claim_type: str
    summary: str
    outcome: str
    amount_paid: float


class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: str
    date_of_birth: str
    address: Address
    customer_since: str
    previous_claims: list[PreviousClaim]


class Handler(BaseModel):
    handler_id: str
    name: str
    role: str
    email: str
    can_approve_over_limit: bool


class PolicyWording(BaseModel):
    version: str
    text: str


class Instructions(BaseModel):
    text: str


class StartClaim(BaseModel):
    thread_id: str


class NewStep(BaseModel):
    kind: Literal["tool", "note"]
    title: str
    detail: str


class Step(NewStep):
    step_id: int
    claim_id: str
    created_at: str


class NewDecision(BaseModel):
    decision: Decision
    payout: Money
    reasons: str
    policy_section: str


class Payment(BaseModel):
    amount: Money


class SignOff(BaseModel):
    handler_id: str
