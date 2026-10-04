import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Set once by the tool's owner (see owner/SETUP.md): the web-app link of the Google Apps Script
# that receives each user's name and email. While this is empty nothing is collected and the
# welcome screen shows no notice.
OWNER_REGISTRATION_URL = ""
_APPS_SCRIPT_PREFIX = "https://script.google.com/macros/s/"


def _default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "NaukriJobAutomation"
    return Path.home() / ".naukri_job_automation"


class Config(BaseSettings):
    """Machine-level settings. Anything the user changes day to day lives in the database."""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_prefix="NJA_", extra="ignore")

    # Kept outside the project folder: OneDrive locks live SQLite and browser-profile files.
    data_dir: Path = Field(default_factory=_default_data_dir)
    resumes_dir: Path = PROJECT_ROOT / "resumes"
    max_cv_size_mb: int = 5
    registration_url: str = OWNER_REGISTRATION_URL

    @property
    def registration_enabled(self) -> bool:
        """Only a Google Apps Script link over HTTPS counts; anything else is treated as off."""
        return self.registration_url.startswith(_APPS_SCRIPT_PREFIX)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "data.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


config = Config()
