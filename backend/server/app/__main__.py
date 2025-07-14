# main.py

from fastapi import FastAPI
from backend.server.app.router import register_routes

app = FastAPI()

register_routes(app)

if __name__ == "__main__":

    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)