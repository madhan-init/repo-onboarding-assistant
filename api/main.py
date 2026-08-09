from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from api.routes_ask import router as ask_router
from api.routes_index import router as index_router
from api.routes_overview import router as overview_router
import os

app = FastAPI(title="Repo Onboarding Assistant API")

app.include_router(ask_router)
app.include_router(index_router)
app.include_router(overview_router)

@app.get("/")
def read_root():
    return FileResponse("static/app.html")

# Ensure static dir exists
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

