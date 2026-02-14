import sys
import os
import traceback

# Ensure the backend root is on the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from server import app
except Exception as e:
    # Log the full traceback so we can debug on Vercel
    error_msg = traceback.format_exc()
    print(f"IMPORT ERROR: {error_msg}", file=sys.stderr)

    # Create a minimal FastAPI app that returns the error
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    app = FastAPI()

    @app.get("/{path:path}")
    @app.post("/{path:path}")
    @app.options("/{path:path}")
    async def error_handler(path: str = ""):
        return PlainTextResponse(
            f"Server import failed:\n\n{error_msg}",
            status_code=500,
        )
