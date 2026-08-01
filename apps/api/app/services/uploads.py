class UploadValidationError(ValueError):
    pass


def validate_uploaded_screenshot(
    image_bytes: bytes,
    content_type: str | None,
    max_upload_bytes: int,
    allowed_content_types: str,
) -> None:
    if not image_bytes:
        raise UploadValidationError("스크린샷 업로드가 비어 있습니다.")

    if len(image_bytes) > max_upload_bytes:
        raise UploadValidationError(f"스크린샷 업로드가 너무 큽니다. 최대 크기는 {max_upload_bytes}바이트입니다.")

    allowed = {content_type.strip().lower() for content_type in allowed_content_types.split(",") if content_type.strip()}
    if content_type and allowed and content_type.lower() not in allowed:
        raise UploadValidationError(
            f"지원되지 않는 스크린샷 형식입니다: {content_type}. 허용 형식: {', '.join(sorted(allowed))}."
        )
