"""Cloud Run Jobs dispatch uses the runtime identity, never a service-account key."""

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from engine.jobs.repository import Job

LONG_TYPES = frozenset(
    {
        "srs.optimize",
        "anki.import",
        "anki.export",
        "account.export",
        "account.delete",
        "mock.build",
        "ingest.past_exam",
        "maintenance.probe_long",
    }
)


class MetadataToken(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    access_token: SecretStr
    expires_in: int = Field(gt=0)
    token_type: str


class CloudRunDispatcher:
    def __init__(self, project: str, region: str) -> None:
        self.url = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/sf-engine-long:run"

    async def dispatch(self, job: Job) -> None:
        async with httpx.AsyncClient(timeout=15, trust_env=False, follow_redirects=False) as client:
            response = await client.get(
                "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
            )
            response.raise_for_status()
            token = MetadataToken.model_validate(response.json())
            response = await client.post(
                self.url,
                headers={
                    "Authorization": "Bearer " + token.access_token.get_secret_value(),
                },
                json={
                    "overrides": {
                        "containerOverrides": [
                            {
                                "args": [
                                    "--job-id",
                                    job.job_id,
                                    "--user-id",
                                    job.user_id,
                                    "--lease-token",
                                    job.lease_token,
                                ]
                            }
                        ]
                    }
                },
            )
            if response.status_code not in (200, 201):
                raise RuntimeError("Long job dispatch failed")
            # An accepted operation is not job completion. The batch process must claim the lease.
