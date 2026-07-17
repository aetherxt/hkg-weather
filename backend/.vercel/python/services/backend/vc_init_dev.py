# Auto-generated trampoline used by vercel dev (Python, ASGI/WSGI)

import os

os.environ.update(
    {
        "VERCEL_DEV_MODULE_NAME": "app.main",
        "VERCEL_DEV_ENTRY_ABS": "/home/aether/Documents/hkg-weather/backend/app/main.py",
        "VERCEL_DEV_FRAMEWORK": "fastapi",
        "VERCEL_DEV_VARIABLE_NAME": "app",
    }
)

from vercel_runtime.dev import main  # noqa: E402

if __name__ == "__main__":
    main()
