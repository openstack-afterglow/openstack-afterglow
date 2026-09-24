"""boto3 기반 S3 wrapper. Ceph RGW S3 endpoint 대상.

백엔드 프록시 업로드 흐름 (Phase 9):
  client → backend (form) → quarantine bucket → 검증 → target bucket (server-side copy)
"""

from __future__ import annotations

import hmac
import logging

_logger = logging.getLogger(__name__)


def get_user_s3_client(token: str, user_id: str, project_id: str):
    """Keystone EC2 credentials → boto3 S3 client (SigV4, path addressing)."""
    import boto3
    import boto3.session

    from app.config import get_settings
    from app.services.keystone import ensure_ec2_credentials

    creds = ensure_ec2_credentials(token, user_id, project_id)
    settings = get_settings()
    # boto3 1.36+ 기본 동작은 모든 요청에 CRC32 등 추가 checksum 을 계산하는데,
    # Ceph RGW 가 이 헤더를 SHA256 hash 로 오해해 XAmzContentSHA256Mismatch 로
    # multipart upload_part 가 실패한다. when_required 로 명시해 회피.
    return boto3.client(
        "s3",
        endpoint_url=settings.os_s3_endpoint,
        aws_access_key_id=creds["access"],
        aws_secret_access_key=creds["secret"],
        region_name="default",
        config=boto3.session.Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def ensure_bucket(client, bucket: str) -> None:
    """버킷이 없으면 생성. 있든 없든 CORS 는 항상 최신 cors_origins 로 재적용 (idempotent)."""
    from botocore.exceptions import ClientError

    try:
        client.head_bucket(Bucket=bucket)
        exists = True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            client.create_bucket(Bucket=bucket)
            _logger.info("quarantine 버킷 생성: %s", bucket)
            exists = False
        else:
            raise

    try:
        _put_bucket_cors(client, bucket)
        _logger.debug("quarantine 버킷 CORS 갱신: %s (existing=%s)", bucket, exists)
    except Exception:
        _logger.warning("quarantine 버킷 CORS 갱신 실패: %s", bucket, exc_info=True)


def _put_bucket_cors(client, bucket: str) -> None:
    """RGW bucket CORS 설정. Phase 9 흐름에서는 백엔드 프록시 업로드를 쓰므로 사실상
    불필요하지만, presigned URL flow 호환을 위해 idempotent 유지. 단 origin/header 는
    `settings.cors_origin_list` 화이트리스트로 좁힌다 — wildcard `*` 는 사용하지 않는다.

    화이트리스트가 비어 있으면 CORS rule 자체를 제거해 cross-origin 접근을 차단.
    """
    from app.config import get_settings

    settings = get_settings()
    origins = settings.cors_origin_list or []
    if not origins:
        try:
            client.delete_bucket_cors(Bucket=bucket)
        except Exception:
            pass
        return
    client.put_bucket_cors(
        Bucket=bucket,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedOrigins": origins,
                    "AllowedMethods": ["PUT", "POST", "GET", "HEAD"],
                    # presigned URL 사용 시 필요한 헤더만 명시적으로 허용
                    "AllowedHeaders": [
                        "Content-Type",
                        "Content-Length",
                        "Content-MD5",
                        "Authorization",
                        "x-amz-content-sha256",
                        "x-amz-date",
                        "x-amz-security-token",
                        "x-amz-user-agent",
                    ],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3600,
                }
            ]
        },
    )


class UploadCanceled(Exception):
    """클라이언트 disconnect 등으로 업로드가 취소되었을 때 raise."""


MULTIPART_THRESHOLD = 8 * 1024 * 1024
MULTIPART_CHUNKSIZE = 8 * 1024 * 1024


class IntegrityError(Exception):
    """저장된 객체가 업로드한 내용과 일치하지 않는다."""


def stream_upload_to_quarantine(
    client,
    quarantine_bucket: str,
    key: str,
    file_stream,
    content_type: str,
    cancel_event=None,
    metadata: dict[str, str] | None = None,
) -> None:
    """boto3 upload_fileobj + TransferConfig 로 quarantine 버킷에 streaming upload.

    5 GB 이상은 자동 multipart upload, 5 TiB 까지 단일 호출로 처리한다.
    file_stream 은 SpooledTemporaryFile 등 read/seek 지원 객체여야 한다.

    metadata 는 업로드 시점에 부착한다. 이후 server-side copy 는 기본
    ``MetadataDirective=COPY`` 이므로 ContentType 과 user metadata 가 대상
    객체까지 그대로 따라간다.

    cancel_event (threading.Event) 가 set 되면 다음 part 진행 시점에
    UploadCanceled 를 raise → boto3 가 multipart 자동 abort.
    """
    from boto3.s3.transfer import TransferConfig

    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        multipart_chunksize=MULTIPART_CHUNKSIZE,
        max_concurrency=4,
        use_threads=True,
    )

    def _progress(_bytes_amount: int) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise UploadCanceled("client disconnected")

    extra: dict = {"ContentType": content_type}
    if metadata:
        extra["Metadata"] = metadata

    client.upload_fileobj(
        Fileobj=file_stream,
        Bucket=quarantine_bucket,
        Key=key,
        ExtraArgs=extra,
        Config=config,
        Callback=_progress,
    )


def verify_quarantine_object(client, bucket: str, key: str, *, expected_size: int, expected_md5: str) -> dict:
    """HEAD 한 번으로 저장된 바이트가 업로드한 내용과 같은지 확인한다.

    단일 PUT 객체의 ETag 는 content MD5 이므로 그대로 비교한다. Multipart 는
    part 별 MD5 의 다이제스트라 내용 해시가 아니며, ``s3transfer`` 가 chunk
    크기를 조정할 수 있는 영역(10 000 parts 초과, 약 80 GiB)은 이 경로의
    상한(기본 10 GB) 밖이므로 size 와 part 수를 불변식으로 검증한다.
    객체 전체를 다시 내려받지 않는다 — 10 GiB 업로드가 20 GiB 다운로드가 된다.
    """
    head = client.head_object(Bucket=bucket, Key=key)
    size = int(head.get("ContentLength", -1))
    etag = (head.get("ETag") or "").strip('"')
    if size != expected_size:
        raise IntegrityError("size mismatch")
    if "-" not in etag:
        if not hmac.compare_digest(etag, expected_md5):
            raise IntegrityError("etag mismatch")
        return head
    try:
        parts = int(etag.rsplit("-", 1)[1])
    except ValueError:
        raise IntegrityError("etag mismatch") from None
    expected_parts = max(1, -(-expected_size // MULTIPART_CHUNKSIZE))
    if parts != expected_parts:
        raise IntegrityError("multipart part count mismatch")
    return head


def copy_object(client, src_bucket: str, src_key: str, dst_bucket: str, dst_key: str) -> None:
    """S3 server-side copy. boto3 client.copy() 가 5 GiB 초과 시 자동 multipart copy."""
    client.copy(
        CopySource={"Bucket": src_bucket, "Key": src_key},
        Bucket=dst_bucket,
        Key=dst_key,
    )


def delete_object(client, bucket: str, key: str) -> None:
    """S3 객체 삭제."""
    client.delete_object(Bucket=bucket, Key=key)


def move_to_target(
    client,
    quarantine_bucket: str,
    target_bucket: str,
    key: str,
    expected_size: int | None = None,
) -> dict:
    """quarantine → target server-side copy + quarantine 원본 삭제.

    데이터는 RGW 안에서 이동하므로 백엔드 통과 바이트는 0이다. expected_size 가
    주어지면 승격된 객체의 크기를 확인하고, 어긋나면 대상 객체를 지운 뒤 실패한다.
    """
    copy_object(client, quarantine_bucket, key, target_bucket, key)
    head = client.head_object(Bucket=target_bucket, Key=key)
    if expected_size is not None and int(head.get("ContentLength", -1)) != expected_size:
        delete_object(client, target_bucket, key)
        raise IntegrityError("target size mismatch")
    delete_object(client, quarantine_bucket, key)
    return {
        "name": key,
        "bytes": head.get("ContentLength", 0),
        "etag": (head.get("ETag", "") or "").strip('"'),
        "content_type": head.get("ContentType", ""),
    }
