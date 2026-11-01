from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import candidates, materials, routes
from app.config import get_settings
from app.storage.scoped import NotOwner

settings = get_settings()
app = FastAPI(title="LumiLattice API", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(NotOwner)
def not_owner(_: Request, exc: NotOwner) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"detail": f"Only the owner can change {exc}. Revise it to make your own version."},
    )


app.include_router(routes.router)
app.include_router(materials.router)
app.include_router(candidates.router)
