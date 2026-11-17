"""Stage 1 - Ingest.

Validates incoming files (images, PDFs, voice notes): type, size and
integrity checks, then preprocessing such as EXIF orientation fixes,
resizing to MAX_IMAGE_LONG_SIDE and PDF page rasterisation.
"""
