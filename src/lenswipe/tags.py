"""Human-readable names for the EXIF tags we surface in reports.

Only the common photographic tags are tabled; unknown tags render as
``tag 0x1234`` in the IFD they came from (never as a lookup failure).
GPS tags keep their sub-IFD identity: ``GPS:GPSLatitude``.
"""

# TIFF/EXIF value types (TIFF 6.0 table) -> (name, bytes per element)
TIFF_TYPES = {
    1: ("BYTE", 1),
    2: ("ASCII", 1),
    3: ("SHORT", 2),
    4: ("LONG", 4),
    5: ("RATIONAL", 8),
    6: ("SBYTE", 1),
    7: ("UNDEFINED", 1),
    8: ("SSHORT", 2),
    9: ("SLONG", 4),
    10: ("SRATIONAL", 8),
    11: ("FLOAT", 4),
    12: ("DOUBLE", 8),
}

IFD0_TAGS = {
    0x0100: "ImageWidth",
    0x0101: "ImageLength",
    0x0102: "BitsPerSample",
    0x0103: "Compression",
    0x0106: "PhotometricInterpretation",
    0x010E: "ImageDescription",
    0x010F: "Make",
    0x0110: "Model",
    0x0111: "StripOffsets",
    0x0112: "Orientation",
    0x0115: "SamplesPerPixel",
    0x011A: "XResolution",
    0x011B: "YResolution",
    0x0128: "ResolutionUnit",
    0x0131: "Software",
    0x0132: "DateTime",
    0x013B: "Artist",
    0x013E: "WhitePoint",
    0x013F: "PrimaryChromaticities",
    0x0211: "YCbCrCoefficients",
    0x0213: "YCbCrPositioning",
    0x0214: "ReferenceBlackWhite",
    0x8298: "Copyright",
    0x8769: "ExifIFDPointer",
    0x8825: "GPSInfoIFDPointer",
    0x8830: "SensitivityType",
    0xA001: "ColorSpace",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
    0xA420: "ImageUniqueID",
}

EXIF_TAGS = {
    0x829A: "ExposureTime",
    0x829D: "FNumber",
    0x8822: "ExposureProgram",
    0x8824: "SpectralSensitivity",
    0x8827: "ISOSpeedRatings",
    0x8830: "SensitivityType",
    0x8832: "RecommendedExposureIndex",
    0x9000: "ExifVersion",
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
    0x9010: "OffsetTime",
    0x9201: "ShutterSpeedValue",
    0x9202: "ApertureValue",
    0x9204: "ExposureBiasValue",
    0x9205: "MaxApertureValue",
    0x9207: "MeteringMode",
    0x9208: "LightSource",
    0x9209: "Flash",
    0x920A: "FocalLength",
    0x927C: "MakerNote",
    0x9286: "UserComment",
    0x9290: "SubSecTime",
    0xA000: "FlashpixVersion",
    0xA002: "PixelXDimension",
    0xA003: "PixelYDimension",
    0xA300: "FileSource",
    0xA301: "SceneType",
    0xA401: "CustomRendered",
    0xA402: "ExposureMode",
    0xA403: "WhiteBalance",
    0xA404: "DigitalZoomRatio",
    0xA405: "FocalLengthIn35mmFilm",
    0xA406: "SceneCaptureType",
    0xA430: "CameraOwnerName",
    0xA431: "BodySerialNumber",
    0xA432: "LensSpecification",
    0xA433: "LensMake",
    0xA434: "LensModel",
    0xA435: "LensSerialNumber",
}

GPS_TAGS = {
    0x0000: "GPSVersionID",
    0x0001: "GPSLatitudeRef",
    0x0002: "GPSLatitude",
    0x0003: "GPSLongitudeRef",
    0x0004: "GPSLongitude",
    0x0005: "GPSAltitudeRef",
    0x0006: "GPSAltitude",
    0x0007: "GPSTimeStamp",
    0x0008: "GPSSatellites",
    0x000B: "GPSStatus",
    0x000C: "GPSMeasureMode",
    0x001D: "GPSDateStamp",
}


def tag_name(tag: int, table: dict[int, str] | None = None) -> str:
    if table and tag in table:
        return table[tag]
    if tag in IFD0_TAGS:
        return IFD0_TAGS[tag]
    return f"tag 0x{tag:04X}"