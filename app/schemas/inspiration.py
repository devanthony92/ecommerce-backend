from datetime import datetime
from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints, UrlConstraints

from app.models.inspiration import URL_LENGTH
from app.schemas.base import CamelModel

# URL http(s) válida. Se guarda como texto (model_dump(mode="json")).
Url = Annotated[HttpUrl, UrlConstraints(max_length=URL_LENGTH, allowed_schemes=["http", "https"])]


class InspirationIn(CamelModel):
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    pexels_id: int = Field(gt=0)
    alt: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] = ""
    photographer: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    photographer_url: Url
    link: Url
    image: Url


class InspirationOut(CamelModel):
    """Lo que ve el cliente. El dueño (owner_id) no se expone."""

    id: int
    keyword: str
    pexels_id: int
    alt: str
    photographer: str
    photographer_url: str
    link: str
    image: str
    created_at: datetime
