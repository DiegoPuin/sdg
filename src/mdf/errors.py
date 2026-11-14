"""Excepciones del framework y su código de salida."""


class MdfError(Exception):
    exit_code = 1


class MetadataError(MdfError):
    exit_code = 2


class ReadError(MdfError):
    exit_code = 3


class TransformError(MdfError):
    exit_code = 4


class WriteError(MdfError):
    exit_code = 5
