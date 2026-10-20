from fastapi import FastAPI

from ph_energy_data.api.errors import install_error_handlers
from ph_energy_data.api.v1 import router as v1

app = FastAPI(title="PH Energy Rates", version="0.1.0")
install_error_handlers(app)
app.include_router(v1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
