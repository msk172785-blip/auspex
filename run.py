"""Convenience launcher. Equivalent to: uvicorn app.main:app --reload"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"\n  Autonomous Analyst → http://{settings.HOST}:{settings.PORT}\n")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
