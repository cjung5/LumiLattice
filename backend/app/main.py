from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import candidates, materials, routes
from app.config import get_settings

app = FastAPI(title="LumiLattice API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(routes.router)
app.include_router(materials.router)
app.include_router(candidates.router)
