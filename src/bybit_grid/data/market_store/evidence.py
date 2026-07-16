from __future__ import annotations

import binascii
import ctypes
import errno
import hashlib
import os
import re
import secrets
import stat
import struct
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from ..public_batch.evidence import validate_review_pack
from ..public_batch.models import PublicBatchError
from .audit import audit_market_store
from .canonical import canonical_json_bytes
from .models import (
    STORE_SCHEMA_VERSION,
    MarketStoreError,
)
from .parsing import parse_import_receipt_bytes, parse_seed_manifest_bytes
from .paths import evidence_rel, receipt_rel


SEED_REVIEW_PACK_SCHEMA = "bybit_public_parquet_seed_review_pack_v1"
_MANIFEST_NAME = "review_pack_manifest.json"
_AUDIT_NAME = "store_audit.json"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_READ_SIZE = 1024 * 1024
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_MAX_MEMBER_COUNT = 4096
_MAX_MEMBER_BYTES = 128 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
_MAX_CONTROL_MEMBER_BYTES = 4 * 1024 * 1024
_MAX_MEMBER_NAME_BYTES = 1024
_MAX_CENTRAL_DIRECTORY_BYTES = 8 * 1024 * 1024
_REGULAR_EXTERNAL_ATTR = (stat.S_IFREG | 0o600) << 16
_LEGACY_EMPTY_MANIFEST_BYTES = b'{"members":{}}\n'
_LOCAL_HEADER = struct.Struct("<4s5H3L2H")
_CENTRAL_HEADER = struct.Struct("<4s6H3L5H2L")
_END_RECORD = struct.Struct("<4s4H2LH")
_RENAME_NOREPLACE = 1
_SEED_INSTALL_TEMP_PREFIX = ".bybit-grid-seed-install-"


def _absolute_lexical_path(value, error_code):
    try:
        return Path(os.path.abspath(os.fspath(value)))
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError(error_code) from exc


def _resolved_path(value, error_code):
    try:
        return Path(os.path.realpath(os.fspath(value)))
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError(error_code) from exc


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _safe_member_name(name):
    has_control = type(name) is str and any(
        ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF for char in name
    )
    if (
        type(name) is not str
        or not name
        or name.startswith("/")
        or "\\" in name
        or ":" in name
        or has_control
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise MarketStoreError("unsafe_zip_path")
    return name


def _is_receipt_member(name):
    parts = name.split("/")
    return (
        len(parts) == 4
        and parts[0] == "imports"
        and parts[1].startswith("run_id=")
        and parts[2].startswith("source_sha256=")
        and parts[3] == "import_receipt.json"
    )


def _stat_identity(value):
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


@contextmanager
def _open_regular_no_follow(path: Path, error_code: str):
    fd = None
    stream = None
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise MarketStoreError(error_code)
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (before.st_dev, before.st_ino):
            raise MarketStoreError(error_code)
        stream = os.fdopen(fd, "rb", closefd=True)
        fd = None
    except MarketStoreError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    except (OSError, TypeError, ValueError) as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise MarketStoreError(error_code) from exc

    try:
        yield stream
        try:
            after = os.fstat(stream.fileno())
            rebound = path.lstat()
        except (OSError, TypeError, ValueError) as exc:
            raise MarketStoreError(error_code) from exc
        if (
            _stat_identity(after) != _stat_identity(opened)
            or not stat.S_ISREG(rebound.st_mode)
            or (rebound.st_dev, rebound.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise MarketStoreError(error_code)
    finally:
        if stream is not None:
            error_in_flight = sys.exc_info()[0] is not None
            try:
                stream.close()
            except OSError as exc:
                if not error_in_flight:
                    raise MarketStoreError(error_code) from exc
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _hash_regular_file(path: Path, error_code: str) -> str:
    digest = hashlib.sha256()
    with _open_regular_no_follow(path, error_code) as stream:
        while True:
            try:
                block = stream.read(_READ_SIZE)
            except (OSError, ValueError) as exc:
                raise MarketStoreError(error_code) from exc
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _read_regular_file(path: Path, error_code: str) -> bytes:
    out = bytearray()
    with _open_regular_no_follow(path, error_code) as stream:
        while True:
            try:
                block = stream.read(_READ_SIZE)
            except (OSError, ValueError) as exc:
                raise MarketStoreError(error_code) from exc
            if not block:
                break
            out.extend(block)
    return bytes(out)


def _inventory_store_files(root: Path):
    files = []
    stack = [(root, "")]
    while stack:
        directory, prefix = stack.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name, reverse=True)
        except (OSError, TypeError, ValueError) as exc:
            raise MarketStoreError("seed_store_inventory_invalid") from exc
        for entry in entries:
            name = f"{prefix}/{entry.name}" if prefix else entry.name
            _safe_member_name(name)
            try:
                if entry.is_symlink():
                    raise MarketStoreError("seed_store_inventory_invalid")
                if entry.is_dir(follow_symlinks=False):
                    stack.append((Path(entry.path), name))
                elif entry.is_file(follow_symlinks=False):
                    files.append((name, Path(entry.path)))
                else:
                    raise MarketStoreError("seed_store_inventory_invalid")
            except MarketStoreError:
                raise
            except OSError as exc:
                raise MarketStoreError("seed_store_inventory_invalid") from exc
    files.sort(key=lambda item: item[0])
    return tuple(files)


def _receipt_from_files(files):
    receipts = [(name, path) for name, path in files if _is_receipt_member(name)]
    if len(receipts) != 1:
        raise MarketStoreError("seed_receipt_count_invalid")
    name, path = receipts[0]
    receipt = parse_import_receipt_bytes(_read_regular_file(path, "seed_store_inventory_invalid"))
    if name != receipt_rel(receipt.run_id, receipt.source_review_pack_sha256).as_posix():
        raise MarketStoreError("seed_receipt_identity_invalid")
    return receipt


def _builder_source_size(files):
    if len(files) + 2 > _MAX_MEMBER_COUNT:
        raise MarketStoreError("seed_zip_limits_invalid")
    names = [name for name, _path in files]
    folded_names = {name.casefold() for name in names}
    if (
        len(folded_names) != len(names)
        or _AUDIT_NAME.casefold() in folded_names
        or _MANIFEST_NAME.casefold() in folded_names
    ):
        raise MarketStoreError("seed_store_inventory_invalid")
    total_size = 0
    for name, path in files:
        try:
            encoded_name = name.encode("ascii")
        except UnicodeEncodeError as exc:
            raise MarketStoreError("seed_store_inventory_invalid") from exc
        if len(encoded_name) > _MAX_MEMBER_NAME_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
        try:
            source_stat = path.lstat()
        except (OSError, TypeError, ValueError) as exc:
            raise MarketStoreError("seed_store_inventory_invalid") from exc
        if not stat.S_ISREG(source_stat.st_mode):
            raise MarketStoreError("seed_store_inventory_invalid")
        if source_stat.st_size > _MAX_MEMBER_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
        total_size += source_stat.st_size
        if total_size > _MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
    return total_size


def _validate_builder_controls(files, source_size, audit_bytes, manifest_bytes):
    if (
        len(audit_bytes) > _MAX_CONTROL_MEMBER_BYTES
        or len(manifest_bytes) > _MAX_CONTROL_MEMBER_BYTES
    ):
        raise MarketStoreError("seed_zip_limits_invalid")
    if source_size + len(audit_bytes) + len(manifest_bytes) > _MAX_TOTAL_UNCOMPRESSED_BYTES:
        raise MarketStoreError("seed_zip_limits_invalid")
    names = [name for name, _path in files] + [_AUDIT_NAME, _MANIFEST_NAME]
    name_sizes = [len(name.encode("ascii")) for name in names]
    central_size = sum(_CENTRAL_HEADER.size + name_size for name_size in name_sizes)
    archive_size = (
        source_size
        + len(audit_bytes)
        + len(manifest_bytes)
        + sum(_LOCAL_HEADER.size + name_size for name_size in name_sizes)
        + central_size
        + _END_RECORD.size
    )
    if central_size > _MAX_CENTRAL_DIRECTORY_BYTES or archive_size > _MAX_ARCHIVE_BYTES:
        raise MarketStoreError("seed_zip_limits_invalid")


def _receipt_from_extracted(root: Path, member_names):
    receipt_names = sorted(name for name in member_names if _is_receipt_member(name))
    if len(receipt_names) != 1:
        raise MarketStoreError("seed_receipt_count_invalid")
    name = receipt_names[0]
    receipt = parse_import_receipt_bytes(
        _read_regular_file(root.joinpath(*name.split("/")), "seed_extract_invalid")
    )
    if name != receipt_rel(receipt.run_id, receipt.source_review_pack_sha256).as_posix():
        raise MarketStoreError("seed_receipt_identity_invalid")
    return receipt


def _validate_nested_public_pack(root: Path, receipt):
    nested = root / evidence_rel(receipt.source_review_pack_sha256) / "review_pack.zip"
    try:
        result = validate_review_pack(nested, receipt.run_id)
    except PublicBatchError as exc:
        raise MarketStoreError("nested_public_review_pack_invalid") from exc
    except Exception as exc:
        raise MarketStoreError("nested_public_review_pack_invalid") from exc
    if type(result) is not dict or result.get("ok") is not True:
        raise MarketStoreError("nested_public_review_pack_invalid")


def _regular_zip_info(name):
    info = zipfile.ZipInfo(name, _FIXED_ZIP_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = _REGULAR_EXTERNAL_ATTR
    return info


def _requested_path(value, error_code):
    try:
        return Path(os.fspath(value))
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError(error_code) from exc


def _strict_fspath_text(value, error_code):
    try:
        text = os.fspath(value)
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError(error_code) from exc
    if type(text) is not str:
        raise MarketStoreError(error_code)
    return text


def _same_directory_identity(left, right):
    return (
        stat.S_ISDIR(left.st_mode)
        and stat.S_ISDIR(right.st_mode)
        and (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)
    )


@contextmanager
def _open_seed_install_parent(path: Path):
    fd = None
    try:
        before = path.lstat()
        if not stat.S_ISDIR(before.st_mode):
            raise MarketStoreError("unsafe_seed_install_destination")
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        path_real = _resolved_path(path, "unsafe_seed_install_destination")
        descriptor_real = _resolved_path(
            Path(f"/proc/self/fd/{fd}"),
            "unsafe_seed_install_destination",
        )
        if (
            not _same_directory_identity(before, opened)
            or before.st_mode != opened.st_mode
            or path_real != descriptor_real
        ):
            raise MarketStoreError("unsafe_seed_install_destination")
    except MarketStoreError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    except (OSError, TypeError, ValueError) as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise MarketStoreError("unsafe_seed_install_destination") from exc

    try:
        yield fd, (opened, descriptor_real)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _require_seed_install_parent_bound(path: Path, parent_fd: int, identity):
    opened, opened_real = identity
    try:
        current_path = path.stat(follow_symlinks=False)
        current_fd = os.fstat(parent_fd)
        current_path_real = _resolved_path(path, "unsafe_seed_install_destination")
        current_descriptor_real = _resolved_path(
            Path(f"/proc/self/fd/{parent_fd}"),
            "unsafe_seed_install_destination",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("unsafe_seed_install_destination") from exc
    if (
        not _same_directory_identity(current_path, opened)
        or not _same_directory_identity(current_fd, opened)
        or current_path.st_mode != opened.st_mode
        or current_fd.st_mode != opened.st_mode
        or current_path_real != opened_real
        or current_descriptor_real != opened_real
    ):
        raise MarketStoreError("unsafe_seed_install_destination")


def _require_seed_install_destination_absent(parent_fd: int, name: str):
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("unsafe_seed_install_destination") from exc
    raise MarketStoreError("seed_install_destination_exists")


def _directory_entry_matches_descriptor(parent_fd: int, name: str, descriptor_fd: int) -> bool:
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(descriptor_fd)
    except (OSError, TypeError, ValueError):
        return False
    return _same_directory_identity(entry, opened)


def _remove_created_seed_install_directory(parent_fd: int, created):
    try:
        if created is None or not stat.S_ISDIR(created.st_mode):
            raise MarketStoreError("seed_install_cleanup_invalid")
        with os.scandir(parent_fd) as iterator:
            parent_names = sorted(entry.name for entry in iterator)
        matching_names = []
        for candidate in parent_names:
            try:
                entry = os.stat(candidate, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if _same_directory_identity(entry, created):
                matching_names.append(candidate)
        if len(matching_names) != 1:
            raise MarketStoreError("seed_install_cleanup_invalid")
        os.rmdir(matching_names[0], dir_fd=parent_fd)
    except MarketStoreError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_install_cleanup_invalid") from exc


def _create_seed_install_temp(parent_fd: int):
    for _attempt in range(32):
        name = f"{_SEED_INSTALL_TEMP_PREFIX}{secrets.token_hex(16)}.tmp"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except (OSError, TypeError, ValueError) as exc:
            raise MarketStoreError("seed_install_temp_unsafe") from exc

        descriptor_fd = None
        created = None
        try:
            created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            os.chmod(
                name,
                0o700,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            normalized = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not _same_directory_identity(created, normalized):
                raise MarketStoreError("seed_install_temp_unsafe")
            flags = os.O_RDONLY
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor_fd = os.open(name, flags, dir_fd=parent_fd)
            opened = os.fstat(descriptor_fd)
            if not _same_directory_identity(created, opened):
                raise MarketStoreError("seed_install_temp_unsafe")
            return name, descriptor_fd
        except (MarketStoreError, OSError, TypeError, ValueError) as exc:
            if descriptor_fd is not None:
                try:
                    os.close(descriptor_fd)
                except OSError:
                    pass
            primary_error = (
                exc
                if isinstance(exc, MarketStoreError)
                else MarketStoreError("seed_install_temp_unsafe")
            )
            try:
                _remove_created_seed_install_directory(parent_fd, created)
            except MarketStoreError as cleanup_error:
                raise cleanup_error from primary_error
            if isinstance(exc, MarketStoreError):
                raise
            raise primary_error from exc
    raise MarketStoreError("seed_install_temp_unsafe")


def _normalize_seed_install_tree(directory_fd: int):
    try:
        with os.scandir(directory_fd) as iterator:
            names = sorted(entry.name for entry in iterator)
        for name in names:
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(entry.st_mode):
                flags = os.O_RDONLY
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_DIRECTORY", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                child_fd = os.open(name, flags, dir_fd=directory_fd)
                try:
                    if not _same_directory_identity(entry, os.fstat(child_fd)):
                        raise MarketStoreError("seed_install_temp_unsafe")
                    _normalize_seed_install_tree(child_fd)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(entry.st_mode):
                flags = os.O_RDONLY
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                flags |= getattr(os, "O_NONBLOCK", 0)
                file_fd = os.open(name, flags, dir_fd=directory_fd)
                try:
                    opened = os.fstat(file_fd)
                    if not stat.S_ISREG(opened.st_mode) or (
                        opened.st_dev,
                        opened.st_ino,
                    ) != (entry.st_dev, entry.st_ino):
                        raise MarketStoreError("seed_install_temp_unsafe")
                    os.fchmod(file_fd, 0o600)
                finally:
                    os.close(file_fd)
            else:
                raise MarketStoreError("seed_install_temp_unsafe")
        os.fchmod(directory_fd, 0o700)
    except MarketStoreError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_install_temp_unsafe") from exc


def _clear_seed_install_directory(directory_fd: int):
    try:
        with os.scandir(directory_fd) as iterator:
            names = sorted((entry.name for entry in iterator), reverse=True)
        for name in names:
            entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(entry.st_mode):
                flags = os.O_RDONLY
                flags |= getattr(os, "O_CLOEXEC", 0)
                flags |= getattr(os, "O_DIRECTORY", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                child_fd = os.open(name, flags, dir_fd=directory_fd)
                try:
                    if not _same_directory_identity(entry, os.fstat(child_fd)):
                        raise MarketStoreError("seed_install_cleanup_invalid")
                    _clear_seed_install_directory(child_fd)
                finally:
                    os.close(child_fd)
                os.rmdir(name, dir_fd=directory_fd)
            else:
                os.unlink(name, dir_fd=directory_fd)
    except MarketStoreError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_install_cleanup_invalid") from exc


def _cleanup_seed_install_temp(parent_fd: int, name: str, temp_fd: int):
    try:
        _clear_seed_install_directory(temp_fd)
        opened = os.fstat(temp_fd)
        with os.scandir(parent_fd) as iterator:
            parent_names = sorted(entry.name for entry in iterator)
        matching_names = []
        for candidate in parent_names:
            try:
                entry = os.stat(candidate, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if _same_directory_identity(entry, opened):
                matching_names.append(candidate)
        if len(matching_names) != 1:
            raise MarketStoreError("seed_install_cleanup_invalid")
        owned_name = matching_names[0]
        if owned_name == name and not _directory_entry_matches_descriptor(
            parent_fd,
            name,
            temp_fd,
        ):
            raise MarketStoreError("seed_install_cleanup_invalid")
        os.rmdir(owned_name, dir_fd=parent_fd)
    except MarketStoreError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_install_cleanup_invalid") from exc


def _rename_seed_install_noreplace(parent_fd, source_name, destination_name):
    try:
        library = ctypes.CDLL(None, use_errno=True)
        renameat2 = library.renameat2
        renameat2.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        renameat2.restype = ctypes.c_int
        source_bytes = os.fsencode(source_name)
        destination_bytes = os.fsencode(destination_name)
        ctypes.set_errno(0)
        result = renameat2(
            parent_fd,
            source_bytes,
            parent_fd,
            destination_bytes,
            _RENAME_NOREPLACE,
        )
        if result == 0:
            return
        error_number = ctypes.get_errno()
        if error_number in (errno.EEXIST, errno.ENOTEMPTY):
            raise MarketStoreError("seed_install_destination_exists")
        raise MarketStoreError("seed_install_publish_invalid")
    except MarketStoreError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_install_publish_invalid") from exc


@contextmanager
def _open_destination_directory(path: Path, root_real: Path):
    fd = None
    try:
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise MarketStoreError("unsafe_seed_destination")
        descriptor_path = Path(f"/proc/self/fd/{fd}")
        directory_real = _resolved_path(descriptor_path, "unsafe_seed_destination")
        if _inside(directory_real, root_real):
            raise MarketStoreError("destination_inside_store")
    except MarketStoreError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    except (OSError, TypeError, ValueError) as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        raise MarketStoreError("unsafe_seed_destination") from exc

    try:
        yield fd, opened
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _directory_is_still_bound(path: Path, opened) -> bool:
    try:
        current = path.stat(follow_symlinks=False)
    except (OSError, TypeError, ValueError):
        return False
    return stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (
        opened.st_dev,
        opened.st_ino,
    )


def _require_destination_directory_bound(path: Path, opened, root_real: Path):
    current_real = _resolved_path(path, "unsafe_seed_destination")
    if _inside(current_real, root_real):
        raise MarketStoreError("destination_inside_store")
    if not _directory_is_still_bound(path, opened):
        raise MarketStoreError("unsafe_seed_destination")


def _create_temp_entry(directory_fd: int):
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(32):
        name = f".bybit-grid-seed-{secrets.token_hex(16)}.tmp"
        try:
            fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            continue
        except (OSError, TypeError, ValueError) as exc:
            raise MarketStoreError("seed_pack_build_invalid") from exc
        return name, fd
    raise MarketStoreError("seed_pack_build_invalid")


def _entry_matches_descriptor(directory_fd: int, name: str, descriptor_fd: int) -> bool:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        opened = os.fstat(descriptor_fd)
    except (OSError, TypeError, ValueError):
        return False
    return stat.S_ISREG(entry.st_mode) and (entry.st_dev, entry.st_ino) == (
        opened.st_dev,
        opened.st_ino,
    )


def _copy_store_file_to_zip(archive, name, path, expected_hash):
    digest = hashlib.sha256()
    info = _regular_zip_info(name)
    with (
        _open_regular_no_follow(path, "seed_store_inventory_invalid") as source,
        archive.open(info, "w") as destination,
    ):
        while True:
            try:
                block = source.read(_READ_SIZE)
            except (OSError, ValueError) as exc:
                raise MarketStoreError("seed_store_inventory_invalid") from exc
            if not block:
                break
            digest.update(block)
            destination.write(block)
    if digest.hexdigest() != expected_hash:
        raise MarketStoreError("seed_store_inventory_invalid")


def _require_store_unchanged(root: Path, original_files, member_hashes):
    current_files = _inventory_store_files(root)
    if [name for name, _path in current_files] != [name for name, _path in original_files]:
        raise MarketStoreError("seed_store_inventory_invalid")
    for name, path in current_files:
        if _hash_regular_file(path, "seed_store_inventory_invalid") != member_hashes[name]:
            raise MarketStoreError("seed_store_inventory_invalid")


def make_seed_review_pack(store_root, dest):
    requested_destination = _requested_path(dest, "unsafe_seed_destination")
    if requested_destination.name in {"", ".", ".."}:
        raise MarketStoreError("unsafe_seed_destination")
    root = _absolute_lexical_path(store_root, "unsafe_store_root")
    destination = _absolute_lexical_path(dest, "unsafe_seed_destination")
    try:
        destination_mode = destination.lstat().st_mode
    except FileNotFoundError:
        destination_mode = None
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("unsafe_seed_destination") from exc
    if destination_mode is not None and not stat.S_ISREG(destination_mode):
        raise MarketStoreError("unsafe_seed_destination")
    root_real = _resolved_path(root, "unsafe_store_root")
    destination_real = _resolved_path(destination, "unsafe_seed_destination")
    destination_entry_real = (
        _resolved_path(destination.parent, "unsafe_seed_destination") / destination.name
    )
    if (
        _inside(destination, root)
        or _inside(destination_real, root_real)
        or _inside(destination_entry_real, root_real)
    ):
        raise MarketStoreError("destination_inside_store")

    with _open_destination_directory(destination.parent, root_real) as (
        destination_directory_fd,
        destination_directory_identity,
    ):
        audit = audit_market_store(root)
        if not audit.ok:
            raise MarketStoreError("store_audit_failed")
        files = _inventory_store_files(root)
        source_size = _builder_source_size(files)
        receipt = _receipt_from_files(files)
        if receipt.storage_schema_version != STORE_SCHEMA_VERSION:
            raise MarketStoreError("seed_identity_mismatch")

        member_hashes = {
            name: _hash_regular_file(path, "seed_store_inventory_invalid") for name, path in files
        }
        audit_bytes = canonical_json_bytes(audit)
        member_hashes[_AUDIT_NAME] = hashlib.sha256(audit_bytes).hexdigest()
        manifest = {
            "members": dict(sorted(member_hashes.items())),
            "run_id": receipt.run_id,
            "schema": SEED_REVIEW_PACK_SCHEMA,
            "source_review_pack_sha256": receipt.source_review_pack_sha256,
            "storage_schema_version": receipt.storage_schema_version,
        }
        manifest_bytes = canonical_json_bytes(manifest)
        _validate_builder_controls(files, source_size, audit_bytes, manifest_bytes)
        store_files = dict(files)

        temp_name, temp_fd = _create_temp_entry(destination_directory_fd)
        try:
            try:
                with os.fdopen(os.dup(temp_fd), "w+b", closefd=True) as output:
                    with zipfile.ZipFile(
                        output,
                        "w",
                        compression=zipfile.ZIP_STORED,
                    ) as archive:
                        for name in sorted(set(member_hashes) | {_MANIFEST_NAME}):
                            if name == _MANIFEST_NAME:
                                archive.writestr(_regular_zip_info(name), manifest_bytes)
                            elif name == _AUDIT_NAME:
                                archive.writestr(_regular_zip_info(name), audit_bytes)
                            else:
                                _copy_store_file_to_zip(
                                    archive,
                                    name,
                                    store_files[name],
                                    member_hashes[name],
                                )
                os.fsync(temp_fd)
                built_identity = _stat_identity(os.fstat(temp_fd))
                built_digest = _hash_open_archive(temp_fd, built_identity[4])
            except MarketStoreError:
                raise
            except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
                raise MarketStoreError("seed_pack_build_invalid") from exc

            stable_temp_path = Path(f"/proc/self/fd/{destination_directory_fd}/{temp_name}")
            check_seed_review_pack(stable_temp_path)
            try:
                with os.fdopen(os.dup(temp_fd), "rb", closefd=True) as checked_source:
                    _check_seed_review_pack_stream(checked_source)
            except MarketStoreError:
                raise
            except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
                raise MarketStoreError("seed_pack_publish_invalid") from exc
            _require_store_unchanged(root, files, member_hashes)
            try:
                current_identity = _stat_identity(os.fstat(temp_fd))
                if current_identity != built_identity:
                    raise MarketStoreError("seed_temp_path_unsafe")
                current_digest = _hash_open_archive(temp_fd, current_identity[4])
            except MarketStoreError as exc:
                raise MarketStoreError("seed_temp_path_unsafe") from exc
            if current_digest != built_digest or not _entry_matches_descriptor(
                destination_directory_fd,
                temp_name,
                temp_fd,
            ):
                raise MarketStoreError("seed_temp_path_unsafe")
            _require_destination_directory_bound(
                destination.parent,
                destination_directory_identity,
                root_real,
            )
            try:
                os.replace(
                    temp_name,
                    destination.name,
                    src_dir_fd=destination_directory_fd,
                    dst_dir_fd=destination_directory_fd,
                )
            except (OSError, TypeError, ValueError) as exc:
                raise MarketStoreError("seed_pack_publish_invalid") from exc
        finally:
            try:
                os.unlink(temp_name, dir_fd=destination_directory_fd)
            except FileNotFoundError:
                pass
            except (OSError, TypeError, ValueError):
                pass
            try:
                os.close(temp_fd)
            except OSError:
                pass
    return requested_destination


def _archive_size(source_pack):
    try:
        size = os.fstat(source_pack.fileno()).st_size
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_zip_invalid") from exc
    if size > _MAX_ARCHIVE_BYTES:
        raise MarketStoreError("seed_zip_limits_invalid")
    return size


def _hash_open_archive(source_pack, size):
    digest = hashlib.sha256()
    offset = 0
    try:
        descriptor_fd = source_pack if type(source_pack) is int else source_pack.fileno()
        while offset < size:
            block = os.pread(descriptor_fd, min(_READ_SIZE, size - offset), offset)
            if not block:
                raise MarketStoreError("unsafe_seed_pack_path")
            digest.update(block)
            offset += len(block)
        if os.fstat(descriptor_fd).st_size != size:
            raise MarketStoreError("unsafe_seed_pack_path")
    except MarketStoreError:
        raise
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("unsafe_seed_pack_path") from exc
    return digest.digest()


def _preflight_end_record(source_pack, archive_size):
    if archive_size < _END_RECORD.size:
        raise MarketStoreError("seed_zip_invalid")
    end_offset = archive_size - _END_RECORD.size
    end_payload = _read_zip_metadata_at(source_pack, end_offset, _END_RECORD.size)
    if end_payload[:4] != b"PK\x05\x06":
        search_size = min(archive_size, 65557)
        tail = _read_zip_metadata_at(source_pack, archive_size - search_size, search_size)
        if b"PK\x05\x06" in tail:
            raise MarketStoreError("seed_zip_metadata_invalid")
        raise MarketStoreError("seed_zip_invalid")
    (
        _signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        comment_size,
    ) = _END_RECORD.unpack(end_payload)
    if (
        disk_number != 0
        or central_disk != 0
        or disk_entries != total_entries
        or comment_size != 0
        or central_offset == 0xFFFFFFFF
        or central_size == 0xFFFFFFFF
        or total_entries == 0xFFFF
        or central_offset + central_size != end_offset
    ):
        raise MarketStoreError("seed_zip_metadata_invalid")
    if total_entries > _MAX_MEMBER_COUNT or central_size > _MAX_CENTRAL_DIRECTORY_BYTES:
        raise MarketStoreError("seed_zip_limits_invalid")
    central_cursor = central_offset
    for _entry_index in range(total_entries):
        if central_cursor + _CENTRAL_HEADER.size > end_offset:
            raise MarketStoreError("seed_zip_metadata_invalid")
        central = _CENTRAL_HEADER.unpack(
            _read_zip_metadata_at(source_pack, central_cursor, _CENTRAL_HEADER.size)
        )
        if central[0] != b"PK\x01\x02":
            raise MarketStoreError("seed_zip_metadata_invalid")
        name_size, extra_size, member_comment_size = central[10:13]
        if name_size > _MAX_MEMBER_NAME_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
        central_cursor += _CENTRAL_HEADER.size + name_size + extra_size + member_comment_size
        if central_cursor > end_offset:
            raise MarketStoreError("seed_zip_metadata_invalid")
    if central_cursor != end_offset:
        raise MarketStoreError("seed_zip_metadata_invalid")


def _validate_zip_limits(infos):
    if len(infos) > _MAX_MEMBER_COUNT:
        raise MarketStoreError("seed_zip_limits_invalid")
    total_size = 0
    for info in infos:
        try:
            encoded_name = info.filename.encode("ascii")
        except UnicodeEncodeError as exc:
            raise MarketStoreError("seed_zip_metadata_invalid") from exc
        if len(encoded_name) > _MAX_MEMBER_NAME_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
        if info.file_size > _MAX_MEMBER_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
        total_size += info.file_size
        if total_size > _MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise MarketStoreError("seed_zip_limits_invalid")
        if (
            info.filename in {_MANIFEST_NAME, _AUDIT_NAME}
            and info.file_size > _MAX_CONTROL_MEMBER_BYTES
        ):
            raise MarketStoreError("seed_zip_limits_invalid")


def _read_zip_metadata_at(source_pack, offset, size):
    try:
        payload = os.pread(source_pack.fileno(), size, offset)
    except (OSError, TypeError, ValueError) as exc:
        raise MarketStoreError("seed_zip_metadata_invalid") from exc
    if len(payload) != size:
        raise MarketStoreError("seed_zip_metadata_invalid")
    return payload


def _validate_zip_layout(source_pack, archive, infos, archive_size):
    if archive_size < _END_RECORD.size:
        raise MarketStoreError("seed_zip_metadata_invalid")
    end_offset = archive_size - _END_RECORD.size
    end_record = _END_RECORD.unpack(
        _read_zip_metadata_at(source_pack, end_offset, _END_RECORD.size)
    )
    (
        signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        comment_size,
    ) = end_record
    if (
        signature != b"PK\x05\x06"
        or disk_number != 0
        or central_disk != 0
        or disk_entries != len(infos)
        or total_entries != len(infos)
        or central_offset != archive.start_dir
        or central_size != end_offset - central_offset
        or comment_size != 0
    ):
        raise MarketStoreError("seed_zip_metadata_invalid")

    local_cursor = 0
    for info in infos:
        try:
            encoded_name = info.filename.encode("ascii")
        except UnicodeEncodeError as exc:
            raise MarketStoreError("seed_zip_metadata_invalid") from exc
        if info.header_offset != local_cursor:
            raise MarketStoreError("seed_zip_metadata_invalid")
        local = _LOCAL_HEADER.unpack(
            _read_zip_metadata_at(source_pack, local_cursor, _LOCAL_HEADER.size)
        )
        (
            local_signature,
            extract_version,
            flag_bits,
            compression,
            modified_time,
            modified_date,
            crc,
            compressed_size,
            file_size,
            name_size,
            extra_size,
        ) = local
        if (
            local_signature != b"PK\x03\x04"
            or extract_version != 20
            or flag_bits != 0
            or compression != zipfile.ZIP_STORED
            or modified_time != 0
            or modified_date != 33
            or crc != info.CRC
            or compressed_size != info.compress_size
            or file_size != info.file_size
            or compressed_size != file_size
            or name_size != len(encoded_name)
            or extra_size != 0
            or _read_zip_metadata_at(
                source_pack,
                local_cursor + _LOCAL_HEADER.size,
                name_size,
            )
            != encoded_name
        ):
            raise MarketStoreError("seed_zip_metadata_invalid")
        local_cursor += _LOCAL_HEADER.size + name_size + info.compress_size
    if local_cursor != central_offset:
        raise MarketStoreError("seed_zip_metadata_invalid")

    central_cursor = central_offset
    for info in infos:
        encoded_name = info.filename.encode("ascii")
        central = _CENTRAL_HEADER.unpack(
            _read_zip_metadata_at(source_pack, central_cursor, _CENTRAL_HEADER.size)
        )
        (
            central_signature,
            created_version,
            extract_version,
            flag_bits,
            compression,
            modified_time,
            modified_date,
            crc,
            compressed_size,
            file_size,
            name_size,
            extra_size,
            member_comment_size,
            member_disk,
            internal_attr,
            external_attr,
            header_offset,
        ) = central
        if (
            central_signature != b"PK\x01\x02"
            or created_version != (3 << 8) | 20
            or extract_version != 20
            or flag_bits != 0
            or compression != zipfile.ZIP_STORED
            or modified_time != 0
            or modified_date != 33
            or crc != info.CRC
            or compressed_size != info.compress_size
            or file_size != info.file_size
            or compressed_size != file_size
            or name_size != len(encoded_name)
            or extra_size != 0
            or member_comment_size != 0
            or member_disk != 0
            or internal_attr != 0
            or external_attr != _REGULAR_EXTERNAL_ATTR
            or header_offset != info.header_offset
            or _read_zip_metadata_at(
                source_pack,
                central_cursor + _CENTRAL_HEADER.size,
                name_size,
            )
            != encoded_name
        ):
            raise MarketStoreError("seed_zip_metadata_invalid")
        central_cursor += _CENTRAL_HEADER.size + name_size
    if central_cursor != end_offset:
        raise MarketStoreError("seed_zip_metadata_invalid")


def _validated_zip_infos(source_pack, archive, archive_size):
    infos = archive.infolist()
    _validate_zip_limits(infos)
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise MarketStoreError("duplicate_zip_member")
    if archive.comment:
        raise MarketStoreError("seed_zip_metadata_invalid")
    for info in infos:
        if info.orig_filename != info.filename:
            raise MarketStoreError("unsafe_zip_path")
        _safe_member_name(info.filename)
        if info.extra or info.comment:
            raise MarketStoreError("seed_zip_metadata_invalid")
        mode = info.external_attr >> 16
        if info.is_dir() or not stat.S_ISREG(mode):
            raise MarketStoreError("zip_member_type_invalid")
        if (
            info.date_time != _FIXED_ZIP_TIME
            or info.create_system != 3
            or info.create_version != 20
            or info.extract_version != 20
            or info.external_attr != _REGULAR_EXTERNAL_ATTR
            or info.compress_type != zipfile.ZIP_STORED
            or info.compress_size != info.file_size
            or info.flag_bits != 0
        ):
            raise MarketStoreError("seed_zip_metadata_invalid")
    if names != sorted(names) or [info.header_offset for info in infos] != sorted(
        info.header_offset for info in infos
    ):
        raise MarketStoreError("seed_zip_metadata_invalid")
    folded_names = {name.casefold() for name in names}
    if len(folded_names) != len(names):
        raise MarketStoreError("zip_path_collision")
    for name in names:
        parts = name.split("/")
        if any(
            "/".join(parts[:index]).casefold() in folded_names for index in range(1, len(parts))
        ):
            raise MarketStoreError("zip_path_collision")
    _validate_zip_layout(source_pack, archive, infos, archive_size)
    return {info.filename: info for info in infos}


def _reject_legacy_empty_manifest(source_pack, archive, archive_size):
    name = _MANIFEST_NAME.encode("ascii")
    payload = _LEGACY_EMPTY_MANIFEST_BYTES
    local_name_offset = _LOCAL_HEADER.size
    payload_offset = local_name_offset + len(name)
    central_offset = payload_offset + len(payload)
    central_name_offset = central_offset + _CENTRAL_HEADER.size
    end_offset = central_name_offset + len(name)
    expected_archive_size = end_offset + _END_RECORD.size
    if archive_size != expected_archive_size:
        return
    infos = archive.infolist()
    if len(infos) != 1:
        return
    info = infos[0]
    try:
        datetime(*info.date_time)
    except (TypeError, ValueError):
        return
    raw = _read_zip_metadata_at(source_pack, 0, archive_size)
    local = _LOCAL_HEADER.unpack(raw[: _LOCAL_HEADER.size])
    central = _CENTRAL_HEADER.unpack(raw[central_offset : central_offset + _CENTRAL_HEADER.size])
    end = _END_RECORD.unpack(raw[end_offset:])
    crc = binascii.crc32(payload)
    if local != (
        b"PK\x03\x04",
        20,
        0,
        zipfile.ZIP_STORED,
        local[4],
        local[5],
        crc,
        len(payload),
        len(payload),
        len(name),
        0,
    ):
        return
    if central != (
        b"PK\x01\x02",
        (3 << 8) | 20,
        20,
        0,
        zipfile.ZIP_STORED,
        local[4],
        local[5],
        crc,
        len(payload),
        len(payload),
        len(name),
        0,
        0,
        0,
        0,
        0o600 << 16,
        0,
    ):
        return
    if end != (
        b"PK\x05\x06",
        0,
        0,
        1,
        1,
        _CENTRAL_HEADER.size + len(name),
        central_offset,
        0,
    ):
        return
    if (
        archive.comment
        or info.filename != _MANIFEST_NAME
        or info.orig_filename != _MANIFEST_NAME
        or info.header_offset != 0
        or raw[local_name_offset:payload_offset] != name
        or raw[payload_offset:central_offset] != payload
        or raw[central_name_offset:end_offset] != name
    ):
        return
    raise MarketStoreError("empty_manifest")


def _validated_manifest(manifest_bytes, names):
    manifest = parse_seed_manifest_bytes(manifest_bytes)
    if type(manifest["schema"]) is not str or manifest["schema"] != SEED_REVIEW_PACK_SCHEMA:
        raise MarketStoreError("seed_schema_invalid")
    if (
        type(manifest["storage_schema_version"]) is not str
        or manifest["storage_schema_version"] != STORE_SCHEMA_VERSION
    ):
        raise MarketStoreError("seed_storage_schema_invalid")
    run_id = manifest["run_id"]
    if type(run_id) is not str or ".." in run_id or _RUN_ID_RE.fullmatch(run_id) is None:
        raise MarketStoreError("seed_run_id_invalid")
    source_sha256 = manifest["source_review_pack_sha256"]
    if type(source_sha256) is not str or _SHA256_RE.fullmatch(source_sha256) is None:
        raise MarketStoreError("seed_source_sha256_invalid")
    members = manifest["members"]
    if type(members) is not MappingProxyType or not members:
        raise MarketStoreError("seed_manifest_members_invalid")
    if _MANIFEST_NAME in members or _AUDIT_NAME not in members:
        raise MarketStoreError("seed_manifest_member_set_invalid")
    for name, digest in members.items():
        _safe_member_name(name)
        if type(digest) is not str or _SHA256_RE.fullmatch(digest) is None:
            raise MarketStoreError("seed_manifest_hash_invalid")
    if set(names) != set(members) | {_MANIFEST_NAME}:
        raise MarketStoreError("seed_manifest_member_set_invalid")
    return manifest


def _require_regular_outer_pack(path):
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise MarketStoreError("zip_missing") from exc
    except (OSError, ValueError) as exc:
        raise MarketStoreError("unsafe_seed_pack_path") from exc
    if not stat.S_ISREG(mode):
        raise MarketStoreError("unsafe_seed_pack_path")


def _write_extracted_member(root, name, archive, info, expected_hash):
    destination = root.joinpath(*name.split("/"))
    digest = hashlib.sha256()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(destination, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=True) as output:
                fd = None
                with archive.open(info, "r") as source:
                    while True:
                        block = source.read(_READ_SIZE)
                        if not block:
                            break
                        digest.update(block)
                        output.write(block)
        finally:
            if fd is not None:
                os.close(fd)
    except MarketStoreError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketStoreError("seed_extract_invalid") from exc
    if digest.hexdigest() != expected_hash:
        raise MarketStoreError("zip_member_hash_mismatch")


def _write_seed_install_member(root_fd, name, archive, info, expected_hash):
    parts = name.split("/")
    digest = hashlib.sha256()
    directory_fd = None
    file_fd = None
    opened_file = None
    try:
        directory_fd = os.dup(root_fd)
        directory_flags = os.O_RDONLY
        directory_flags |= getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        for part in parts[:-1]:
            created = False
            try:
                os.mkdir(part, 0o700, dir_fd=directory_fd)
                created = True
            except FileExistsError:
                pass
            entry = os.stat(part, dir_fd=directory_fd, follow_symlinks=False)
            if created:
                os.chmod(
                    part,
                    0o700,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                normalized = os.stat(
                    part,
                    dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                if not _same_directory_identity(entry, normalized):
                    raise MarketStoreError("seed_extract_invalid")
                entry = normalized
            child_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            try:
                if not _same_directory_identity(entry, os.fstat(child_fd)):
                    raise MarketStoreError("seed_extract_invalid")
            except (MarketStoreError, OSError, TypeError, ValueError):
                try:
                    os.close(child_fd)
                except OSError:
                    pass
                raise
            previous_fd = directory_fd
            directory_fd = child_fd
            os.close(previous_fd)

        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        file_flags |= getattr(os, "O_CLOEXEC", 0)
        file_flags |= getattr(os, "O_NOFOLLOW", 0)
        file_flags |= getattr(os, "O_NONBLOCK", 0)
        file_fd = os.open(parts[-1], file_flags, 0o600, dir_fd=directory_fd)
        opened_file = os.fstat(file_fd)
        if not stat.S_ISREG(opened_file.st_mode):
            raise MarketStoreError("seed_extract_invalid")
        with os.fdopen(file_fd, "wb", closefd=True) as output:
            file_fd = None
            with archive.open(info, "r") as source:
                while True:
                    block = source.read(_READ_SIZE)
                    if not block:
                        break
                    digest.update(block)
                    output.write(block)
        final_entry = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(final_entry.st_mode) or (
            final_entry.st_dev,
            final_entry.st_ino,
        ) != (opened_file.st_dev, opened_file.st_ino):
            raise MarketStoreError("seed_extract_invalid")
    except MarketStoreError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketStoreError("seed_extract_invalid") from exc
    finally:
        if file_fd is not None:
            try:
                os.close(file_fd)
            except OSError:
                pass
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                pass
    if digest.hexdigest() != expected_hash:
        raise MarketStoreError("zip_member_hash_mismatch")


def _read_archive_member(archive, info, expected_hash):
    digest = hashlib.sha256()
    out = bytearray()
    try:
        with archive.open(info, "r") as source:
            while True:
                block = source.read(_READ_SIZE)
                if not block:
                    break
                digest.update(block)
                out.extend(block)
    except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketStoreError("seed_zip_invalid") from exc
    if digest.hexdigest() != expected_hash:
        raise MarketStoreError("zip_member_hash_mismatch")
    return bytes(out)


def _validate_extracted_store(root, audit_bytes, manifest):
    member_names = set(manifest["members"]) - {_AUDIT_NAME}
    if sum(_is_receipt_member(name) for name in member_names) != 1:
        raise MarketStoreError("seed_receipt_count_invalid")
    audit = audit_market_store(root)
    if not audit.ok:
        raise MarketStoreError("seed_store_audit_failed")
    if canonical_json_bytes(audit) != audit_bytes:
        raise MarketStoreError("seed_store_audit_mismatch")
    receipt = _receipt_from_extracted(root, member_names)
    if (
        manifest["run_id"] != receipt.run_id
        or manifest["source_review_pack_sha256"] != receipt.source_review_pack_sha256
        or manifest["storage_schema_version"] != receipt.storage_schema_version
    ):
        raise MarketStoreError("seed_identity_mismatch")
    _validate_nested_public_pack(root, receipt)
    return receipt


def _extract_validate_seed_review_pack_stream(
    source_pack,
    root=None,
    *,
    root_fd=None,
    prepare_root=None,
    prepare_root_before_payload=False,
):
    try:
        archive_size = _archive_size(source_pack)
        archive_digest = _hash_open_archive(source_pack, archive_size)
        _preflight_end_record(source_pack, archive_size)
        source_pack.seek(0)
        with zipfile.ZipFile(source_pack) as archive:
            _reject_legacy_empty_manifest(source_pack, archive, archive_size)
            infos = _validated_zip_infos(source_pack, archive, archive_size)
            if _MANIFEST_NAME not in infos:
                raise MarketStoreError("seed_manifest_missing")
            if prepare_root is not None and prepare_root_before_payload:
                root, root_fd = prepare_root()
            with archive.open(infos[_MANIFEST_NAME], "r") as source:
                manifest_bytes = source.read(_MAX_CONTROL_MEMBER_BYTES + 1)
            if len(manifest_bytes) > _MAX_CONTROL_MEMBER_BYTES:
                raise MarketStoreError("seed_zip_limits_invalid")
            manifest = _validated_manifest(manifest_bytes, infos)
            if prepare_root is not None and not prepare_root_before_payload:
                root, root_fd = prepare_root()
            audit_bytes = None
            for name in sorted(manifest["members"]):
                expected_hash = manifest["members"][name]
                if name == _AUDIT_NAME:
                    audit_bytes = _read_archive_member(archive, infos[name], expected_hash)
                elif root_fd is None:
                    _write_extracted_member(
                        root,
                        name,
                        archive,
                        infos[name],
                        expected_hash,
                    )
                else:
                    _write_seed_install_member(
                        root_fd,
                        name,
                        archive,
                        infos[name],
                        expected_hash,
                    )
            if audit_bytes is None:
                raise MarketStoreError("seed_manifest_member_set_invalid")
            receipt = _validate_extracted_store(root, audit_bytes, manifest)
        if _hash_open_archive(source_pack, archive_size) != archive_digest:
            raise MarketStoreError("unsafe_seed_pack_path")
    except MarketStoreError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketStoreError("seed_zip_invalid") from exc

    return receipt, manifest, audit_bytes


def _seed_review_pack_result(receipt, manifest):
    return {
        "ok": True,
        "run_id": receipt.run_id,
        "source_review_pack_sha256": receipt.source_review_pack_sha256,
        "storage_schema_version": receipt.storage_schema_version,
        "member_count": len(manifest["members"]),
    }


def _check_seed_review_pack_stream(source_pack):
    temporary = None

    def prepare_check_root():
        nonlocal temporary
        temporary = tempfile.TemporaryDirectory(prefix="bybit-grid-seed-")
        root = Path(temporary.name) / "store"
        root.mkdir()
        return root, None

    try:
        try:
            receipt, manifest, _audit_bytes = _extract_validate_seed_review_pack_stream(
                source_pack,
                prepare_root=prepare_check_root,
            )
        finally:
            if temporary is not None:
                temporary.cleanup()
    except MarketStoreError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        raise MarketStoreError("seed_zip_invalid") from exc
    return _seed_review_pack_result(receipt, manifest)


def _require_seed_install_stage_audit(root, audit_bytes):
    audit = audit_market_store(root)
    if not audit.ok:
        raise MarketStoreError("seed_store_audit_failed")
    if canonical_json_bytes(audit) != audit_bytes:
        raise MarketStoreError("seed_store_audit_mismatch")


def install_seed_review_pack(path, destination_store_root):
    try:
        entry_directory = Path.cwd()
    except (OSError, ValueError) as exc:
        raise MarketStoreError("unsafe_seed_install_destination") from exc
    destination_text = _strict_fspath_text(
        destination_store_root,
        "unsafe_seed_install_destination",
    )
    if not destination_text or destination_text.rsplit(os.sep, 1)[-1] in {"", ".", ".."}:
        raise MarketStoreError("unsafe_seed_install_destination")
    requested_destination = Path(destination_text)
    anchored_destination = (
        requested_destination
        if requested_destination.is_absolute()
        else entry_directory / requested_destination
    )
    destination_path = _absolute_lexical_path(
        anchored_destination,
        "unsafe_seed_install_destination",
    )
    destination_name = destination_path.name
    if destination_name in {"", ".", ".."} or destination_path == Path(destination_path.anchor):
        raise MarketStoreError("unsafe_seed_install_destination")
    pack_text = _strict_fspath_text(path, "unsafe_seed_pack_path")
    requested_pack = Path(pack_text)
    anchored_pack = (
        requested_pack if requested_pack.is_absolute() else entry_directory / requested_pack
    )
    pack_path = _absolute_lexical_path(anchored_pack, "unsafe_seed_pack_path")
    _require_regular_outer_pack(pack_path)

    with _open_seed_install_parent(destination_path.parent) as (
        parent_fd,
        parent_identity,
    ):
        _require_seed_install_parent_bound(
            destination_path.parent,
            parent_fd,
            parent_identity,
        )
        _require_seed_install_destination_absent(parent_fd, destination_name)
        temp_name = None
        temp_fd = None
        published = False
        root = None

        def prepare_install_root():
            nonlocal temp_name, temp_fd, root
            temp_name, temp_fd = _create_seed_install_temp(parent_fd)
            root = Path(f"/proc/self/fd/{parent_fd}/{temp_name}")
            return root, temp_fd

        try:
            with _open_regular_no_follow(
                pack_path,
                "unsafe_seed_pack_path",
            ) as source_pack:
                receipt, _manifest, audit_bytes = _extract_validate_seed_review_pack_stream(
                    source_pack,
                    prepare_root=prepare_install_root,
                    prepare_root_before_payload=True,
                )

            if not _directory_entry_matches_descriptor(parent_fd, temp_name, temp_fd):
                raise MarketStoreError("seed_install_temp_unsafe")
            _normalize_seed_install_tree(temp_fd)
            if not _directory_entry_matches_descriptor(parent_fd, temp_name, temp_fd):
                raise MarketStoreError("seed_install_temp_unsafe")
            _require_seed_install_stage_audit(root, audit_bytes)
            if not _directory_entry_matches_descriptor(parent_fd, temp_name, temp_fd):
                raise MarketStoreError("seed_install_temp_unsafe")
            _require_seed_install_parent_bound(
                destination_path.parent,
                parent_fd,
                parent_identity,
            )
            _require_seed_install_destination_absent(parent_fd, destination_name)
            try:
                _rename_seed_install_noreplace(
                    parent_fd,
                    temp_name,
                    destination_name,
                )
            except MarketStoreError:
                raise
            except (OSError, TypeError, ValueError) as exc:
                raise MarketStoreError("seed_install_publish_invalid") from exc
            published = True
        finally:
            primary_error = sys.exc_info()[1]
            cleanup_error = None
            if not published and temp_fd is not None and temp_name is not None:
                try:
                    _cleanup_seed_install_temp(parent_fd, temp_name, temp_fd)
                except MarketStoreError as exc:
                    cleanup_error = exc
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except OSError:
                    pass
            if cleanup_error is not None:
                if primary_error is not None:
                    raise cleanup_error from primary_error
                raise cleanup_error
        return receipt


def check_seed_review_pack(path):
    pack_path = _absolute_lexical_path(path, "unsafe_seed_pack_path")
    _require_regular_outer_pack(pack_path)
    with _open_regular_no_follow(pack_path, "unsafe_seed_pack_path") as source_pack:
        return _check_seed_review_pack_stream(source_pack)
