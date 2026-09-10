"""Version 1 HTTP layer: PDF uploads in, screened + ranked candidates out.

`.env` is loaded here, at package import time, because several modules in this
project (`orchestrator.client_job_board`, `agents.*`) read `os.getenv` at import
time. Loading before any of them are imported keeps their configuration working.
"""

from dotenv import load_dotenv

load_dotenv()
