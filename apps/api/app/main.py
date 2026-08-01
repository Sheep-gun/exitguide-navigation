from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analysis, catalog, dark_pattern, navigation, ops, terms
from app.services.navigation_function_catalog import get_navigation_function_catalog


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_navigation_function_catalog()
    yield


app = FastAPI(title="ExitGuide AI API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ops.router)
app.include_router(catalog.router)
app.include_router(terms.router)
app.include_router(analysis.router)
app.include_router(navigation.router)
app.include_router(dark_pattern.router)
