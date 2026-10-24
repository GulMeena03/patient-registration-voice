import re
from datetime import date, datetime
from typing import Annotated, ClassVar, Optional

from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator,
)

STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA",
    "ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK",
    "OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC",
}
SEX_MAP = {
    "male": "Male", "m": "Male", "man": "Male",
    "female": "Female", "f": "Female", "woman": "Female",
    "other": "Other", "non-binary": "Other", "nonbinary": "Other",
    "decline": "Decline to Answer", "decline to answer": "Decline to Answer",
    "prefer not to say": "Decline to Answer", "prefer not to answer": "Decline to Answer",
}
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y")


def parse_dob(v) -> date:
    if isinstance(v, datetime):
        v = v.date()
    if not isinstance(v, date):
        s = str(v).strip()
        for fmt in DATE_FORMATS:
            try:
                v = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        else:
            raise ValueError("date of birth must look like MM/DD/YYYY")
    if v > date.today():
        raise ValueError("date of birth cannot be in the future")
    if v.year < 1900:
        raise ValueError("date of birth must be 1900 or later")
    return v


def normalize_phone(v) -> str:
    digits = re.sub(r"\D", "", str(v))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if not re.fullmatch(r"[2-9]\d{2}[2-9]\d{6}", digits):
        raise ValueError("must be a valid 10-digit U.S. phone number")
    return "+1" + digits


def _name(v: str) -> str:
    v = v.strip()
    if not (1 <= len(v) <= 50) or not any(c.isalpha() for c in v) \
            or not all(c.isalpha() or c in " '-." for c in v):
        raise ValueError("must be 1-50 characters: letters, spaces, hyphens, apostrophes")
    return v


def _state(v: str) -> str:
    v = v.strip().upper()
    if v not in STATES:
        raise ValueError("must be a valid 2-letter U.S. state abbreviation")
    return v


def _zip(v: str) -> str:
    v = v.strip()
    if not re.fullmatch(r"\d{5}(-\d{4})?", v):
        raise ValueError("must be a 5-digit ZIP or ZIP+4")
    return v


def _sex(v: str) -> str:
    out = SEX_MAP.get(str(v).strip().lower())
    if not out:
        raise ValueError("must be Male, Female, Other, or Decline to Answer")
    return out


def _email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", v):
        raise ValueError("invalid email format")
    return v


def _s(n: int, min_length: int = 1):
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=n)


Name = Annotated[str, AfterValidator(_name)]
DOB = Annotated[date, BeforeValidator(parse_dob)]
Phone = Annotated[str, AfterValidator(normalize_phone)]
State = Annotated[str, AfterValidator(_state)]
Zip = Annotated[str, AfterValidator(_zip)]
Sex = Annotated[str, AfterValidator(_sex)]
Email = Annotated[str, AfterValidator(_email)]
Line = Annotated[str, _s(255)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")
    DROP_NONE: ClassVar[bool] = True

    @model_validator(mode="before")
    @classmethod
    def drop_blanks(cls, data):
        if isinstance(data, dict):
            return {
                k: v for k, v in data.items()
                if not (isinstance(v, str) and not v.strip()) and not (v is None and cls.DROP_NONE)
            }
        return data


class PatientCreate(_Base):
    first_name: Name
    last_name: Name
    date_of_birth: DOB
    sex: Sex
    phone_number: Phone
    email: Optional[Email] = None
    address_line_1: Line
    address_line_2: Optional[Line] = None
    city: Annotated[str, _s(100)]
    state: State
    zip_code: Zip
    insurance_provider: Optional[Line] = None
    insurance_member_id: Optional[Annotated[str, _s(100)]] = None
    preferred_language: Annotated[str, _s(50)] = "English"
    emergency_contact_name: Optional[Line] = None
    emergency_contact_phone: Optional[Phone] = None


class PatientUpdate(_Base):
    DROP_NONE: ClassVar[bool] = False  # explicit null clears an optional field
    first_name: Optional[Name] = None
    last_name: Optional[Name] = None
    date_of_birth: Optional[DOB] = None
    sex: Optional[Sex] = None
    phone_number: Optional[Phone] = None
    email: Optional[Email] = None
    address_line_1: Optional[Line] = None
    address_line_2: Optional[Line] = None
    city: Optional[Annotated[str, _s(100)]] = None
    state: Optional[State] = None
    zip_code: Optional[Zip] = None
    insurance_provider: Optional[Line] = None
    insurance_member_id: Optional[Annotated[str, _s(100)]] = None
    preferred_language: Optional[Annotated[str, _s(50)]] = None
    emergency_contact_name: Optional[Line] = None
    emergency_contact_phone: Optional[Phone] = None


REQUIRED_FIELDS = {
    "first_name", "last_name", "date_of_birth", "sex", "phone_number",
    "address_line_1", "city", "state", "zip_code", "preferred_language",
}


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
