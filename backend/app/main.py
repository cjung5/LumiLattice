from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import candidates, materials, routes
from app.config import get_settings

settings = get_settings()
app = FastAPI(title="LumiLattice API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(routes.router)
app.include_router(materials.router)
app.include_router(candidates.router)
