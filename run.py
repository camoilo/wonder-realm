import uvicorn

from app.config import get_config

if __name__ == "__main__":
    cfg = get_config()
    uvicorn.run("app.main:app", host=cfg["server"]["host"], port=cfg["server"]["port"])
