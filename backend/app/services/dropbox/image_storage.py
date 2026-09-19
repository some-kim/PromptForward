"""Dropbox image storage. MongoDB keeps references; Dropbox keeps bytes.

Refresh-token auth keeps the demo alive past the ~4 hour access token lifetime.
"""

from __future__ import annotations

import asyncio
import functools
import io

import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, WriteMode
from PIL import Image

from app.config import get_config
from app.models import ImageMeta, StoredFile

EXTENSION_BY_MIME: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


class ImageStorageError(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def get_dropbox() -> dropbox.Dropbox:
    config = get_config()
    return dropbox.Dropbox(
        app_key=config.dropbox.app_key,
        app_secret=config.dropbox.app_secret,
        oauth2_refresh_token=config.dropbox.refresh_token,
    )


def extension_for(mime_type: str) -> str:
    extension = EXTENSION_BY_MIME.get(mime_type)
    if extension is None:
        raise ImageStorageError(f"Unsupported image type: {mime_type}")
    return extension


async def store_target_image(image_bytes: bytes, image_hash: str, mime_type: str) -> StoredFile:
    """Upload a target image named by its hash. Existing files are reused, so this is idempotent."""
    config = get_config()
    path = f"{config.dropbox.challenges_folder}/{image_hash}.{extension_for(mime_type)}"

    existing = await _get_metadata(path)
    if existing is not None:
        return StoredFile(id=existing.id, path=existing.path_lower or path)

    metadata = await _upload(path, image_bytes, WriteMode.add)
    return StoredFile(id=metadata.id, path=metadata.path_lower or path)


async def store_generated_image(
    attempt_id: str, generation_number: int, image_bytes: bytes, mime_type: str
) -> StoredFile:
    config = get_config()
    extension = extension_for(mime_type)
    path = f"{config.dropbox.generated_folder}/{attempt_id}/{generation_number}.{extension}"
    metadata = await _upload(path, image_bytes, WriteMode.overwrite)
    return StoredFile(id=metadata.id, path=metadata.path_lower or path)


async def download_image(path: str) -> bytes:
    def _download() -> bytes:
        _, response = get_dropbox().files_download(path)
        return response.content

    try:
        return await asyncio.to_thread(_download)
    except ApiError as error:
        raise ImageStorageError(f"Could not download {path}: {error}") from error


async def list_challenge_images() -> list[str]:
    """Paths of every image in the challenges folder."""
    config = get_config()

    def _list() -> list[str]:
        client = get_dropbox()
        paths: list[str] = []
        result = client.files_list_folder(config.dropbox.challenges_folder)
        while True:
            paths.extend(
                entry.path_lower
                for entry in result.entries
                if isinstance(entry, FileMetadata)
                and entry.name.rsplit(".", 1)[-1].lower() in {"png", "jpg", "jpeg", "webp"}
            )
            if not result.has_more:
                return paths
            result = client.files_list_folder_continue(result.cursor)

    try:
        return await asyncio.to_thread(_list)
    except ApiError as error:
        raise ImageStorageError(
            f"Could not list {config.dropbox.challenges_folder}: {error}"
        ) from error


def read_image_meta(image_bytes: bytes) -> ImageMeta:
    with Image.open(io.BytesIO(image_bytes)) as image:
        mime_type = Image.MIME.get(image.format or "", "")
        if not mime_type:
            raise ImageStorageError(f"Unrecognized image format: {image.format}")
        return ImageMeta(width=image.width, height=image.height, mimeType=mime_type)


async def _get_metadata(path: str) -> FileMetadata | None:
    def _metadata() -> FileMetadata | None:
        try:
            entry = get_dropbox().files_get_metadata(path)
        except ApiError:
            return None
        return entry if isinstance(entry, FileMetadata) else None

    return await asyncio.to_thread(_metadata)


async def _upload(path: str, image_bytes: bytes, mode: WriteMode) -> FileMetadata:
    def _do_upload() -> FileMetadata:
        return get_dropbox().files_upload(image_bytes, path, mode=mode)

    try:
        return await asyncio.to_thread(_do_upload)
    except ApiError as error:
        raise ImageStorageError(f"Could not upload {path}: {error}") from error
