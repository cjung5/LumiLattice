from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from app.config import Settings, get_settings
from app.tools.cod import CodClient
from app.tools.literature import OpenAlexClient
from app.tools.literature_sources import (
    ArxivClient,
    CrossrefClient,
    LiteratureSearch,
    SemanticScholarClient,
)
from app.tools.materials import MaterialsProjectClient

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_optional_mp_client(settings: SettingsDep) -> Iterator[MaterialsProjectClient | None]:
    if settings.mp_api_key is None:
        yield None
        return
    client = MaterialsProjectClient(settings.mp_api_key.get_secret_value())
    try:
        yield client
    finally:
        client.close()


def get_mp_client(
    client: Annotated[MaterialsProjectClient | None, Depends(get_optional_mp_client)],
) -> MaterialsProjectClient:
    if client is None:
        raise HTTPException(
            status_code=503, detail="MP_API_KEY is not set. Add it to backend/.env."
        )
    return client


def get_literature_client(settings: SettingsDep) -> Iterator[LiteratureSearch]:
    openalex = settings.openalex_api_key
    s2 = settings.semantic_scholar_api_key
    search = LiteratureSearch(
        [
            OpenAlexClient(openalex.get_secret_value() if openalex else None),
            CrossrefClient(),
            ArxivClient(),
            SemanticScholarClient(s2.get_secret_value() if s2 else None),
        ]
    )
    try:
        yield search
    finally:
        search.close()


def get_cod_client() -> Iterator[CodClient]:
    client = CodClient()
    try:
        yield client
    finally:
        client.close()


OptionalMPDep = Annotated[MaterialsProjectClient | None, Depends(get_optional_mp_client)]
MPDep = Annotated[MaterialsProjectClient, Depends(get_mp_client)]
LiteratureDep = Annotated[LiteratureSearch, Depends(get_literature_client)]
CodDep = Annotated[CodClient, Depends(get_cod_client)]
