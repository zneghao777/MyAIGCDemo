"""Qiniu is a temporary outbound attachment bridge, never primary storage."""

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from functools import cached_property

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.errors import AppError, TransientProviderError


class QiniuTemporaryMedia:
    def __init__(self):
        self.s = get_settings()

    @property
    def configured(self):
        return bool(
            self.s.qiniu_access_key.get_secret_value()
            and self.s.qiniu_secret_key.get_secret_value()
            and self.s.qiniu_s3_bucket
        )

    @cached_property
    def client(self):
        if not self.configured:
            raise AppError("EXTERNAL_MEDIA_NOT_CONFIGURED", "外部素材上传需要配置七牛 AK/SK 和空间名", 503)
        return boto3.client(
            "s3",
            endpoint_url=self.s.qiniu_s3_endpoint,
            region_name=self.s.qiniu_s3_region,
            aws_access_key_id=self.s.qiniu_access_key.get_secret_value(),
            aws_secret_access_key=self.s.qiniu_secret_key.get_secret_value(),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "virtual"},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 2, "mode": "standard"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    async def publish(self, body: bytes, content_type: str) -> str:
        def upload():
            # Reuse identical input within a UTC day. A new date gets a new key,
            # so cleanup can never delete an old key that was just renewed.
            digest = hashlib.sha256(content_type.encode() + b"\0" + body).hexdigest()
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            key = f"{self.s.qiniu_temp_prefix}{day}/{digest}"
            try:
                self.client.head_object(Bucket=self.s.qiniu_s3_bucket, Key=key)
            except ClientError as exc:
                if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 404:
                    raise
                self.client.put_object(
                    Bucket=self.s.qiniu_s3_bucket, Key=key, Body=body, ContentType=content_type
                )
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.s.qiniu_s3_bucket, "Key": key},
                ExpiresIn=self.s.qiniu_signed_url_ttl_seconds,
            )

        try:
            return await asyncio.to_thread(upload)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 500)
            error = TransientProviderError if status >= 500 or status == 429 else AppError
            raise error(
                "EXTERNAL_MEDIA_UPLOAD_FAILED", "七牛临时素材上传失败，请检查空间和访问权限", 502
            ) from None
        except BotoCoreError:
            raise TransientProviderError(
                "EXTERNAL_MEDIA_UPLOAD_FAILED", "七牛临时素材服务暂不可用", 502
            ) from None

    async def cleanup(self):
        if not self.configured:
            return 0

        def remove_expired():
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.s.qiniu_temp_retention_days)
            deleted = 0
            for page in self.client.get_paginator("list_objects_v2").paginate(
                Bucket=self.s.qiniu_s3_bucket, Prefix=self.s.qiniu_temp_prefix
            ):
                for obj in page.get("Contents", []):
                    if obj["Key"].startswith(self.s.qiniu_temp_prefix) and obj["LastModified"] <= cutoff:
                        self.client.delete_object(Bucket=self.s.qiniu_s3_bucket, Key=obj["Key"])
                        deleted += 1
            return deleted

        return await asyncio.to_thread(remove_expired)

    async def configure_lifecycle(self):
        """Explicit setup only; preserve every unrelated bucket lifecycle rule."""

        def configure():
            rule_id = "CineAITemporaryMedia"
            try:
                rules = self.client.get_bucket_lifecycle_configuration(Bucket=self.s.qiniu_s3_bucket)["Rules"]
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in ("NoSuchLifecycleConfiguration", "NoSuchLifecycle"):
                    raise
                rules = []
            rules = [rule for rule in rules if rule.get("ID") != rule_id]
            rules.append(
                {
                    "ID": rule_id,
                    "Status": "Enabled",
                    "Filter": {"Prefix": self.s.qiniu_temp_prefix},
                    "Expiration": {"Days": self.s.qiniu_temp_retention_days},
                }
            )
            self.client.put_bucket_lifecycle_configuration(
                Bucket=self.s.qiniu_s3_bucket, LifecycleConfiguration={"Rules": rules}
            )
            return self.client.get_bucket_lifecycle_configuration(Bucket=self.s.qiniu_s3_bucket)

        return await asyncio.to_thread(configure)
