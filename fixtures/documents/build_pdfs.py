"""Regenerate the small real PDF fixtures without external files or services."""

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)


ROOT = Path(__file__).parent


def text_pdf() -> None:
    writer = PdfWriter()
    for text in (
        "Refunds are available within seven days.",
        "Keep the order number for support.",
    ):
        page = writer.add_blank_page(width=300, height=200)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {
                        NameObject("/F1"): DictionaryObject(
                            {
                                NameObject("/Type"): NameObject("/Font"),
                                NameObject("/Subtype"): NameObject("/Type1"),
                                NameObject("/BaseFont"): NameObject("/Helvetica"),
                            }
                        )
                    }
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 10 100 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(ROOT / "notice.pdf")


def scanned_pdf() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    image = DecodedStreamObject()
    image.set_data(bytes([0, 255, 0, 255] * 4))
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(4),
            NameObject("/Height"): NumberObject(4),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/XObject"): DictionaryObject(
                {NameObject("/Im0"): writer._add_object(image)}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"q 100 0 0 100 10 10 cm /Im0 Do Q")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(ROOT / "scanned.pdf")


if __name__ == "__main__":
    text_pdf()
    scanned_pdf()
