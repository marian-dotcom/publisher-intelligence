"""Create the configured local/CI S3 bucket with bounded retries."""

import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        use_ssl=settings.s3_use_ssl,
    )
    last_error: BotoCoreError | ClientError | None = None
    for _ in range(30):
        try:
            client.create_bucket(Bucket=settings.s3_bucket)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code in {"BucketAlreadyExists", "BucketAlreadyOwnedByYou"}:
                return
            last_error = error
        except BotoCoreError as error:
            last_error = error
        else:
            return
        time.sleep(1)
    raise RuntimeError("object storage did not become ready") from last_error


if __name__ == "__main__":
    main()
