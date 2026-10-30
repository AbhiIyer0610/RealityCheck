from io import BytesIO
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import DocumentStream


PDF_PATH = (
    Path(__file__).parent.parent
    / "fixtures"
    / "refund_policy.pdf"
)


def main() -> None:
    doc_converter = DocumentConverter()
    pdf_bytes = PDF_PATH.read_bytes()

    doc_stream = DocumentStream(
        name=PDF_PATH.name,
        stream=BytesIO(pdf_bytes),
    )

    result = doc_converter.convert(doc_stream)
    document = result.document

    print("\n=== DOCUMENT PAGES ===")
    for page_no, page in document.pages.items():
        print(f"Page number: {page_no}")
        print(f"Page: {page}")
        print(f"Page attributes: {dir(page)}")

    print("\n=== DOCUMENT TYPE ===")
    print(type(document))

    print("\n=== DOCUMENT TEXT ===")
    print(document.export_to_markdown())

    print("\n=== TABLES ===")
    for index, table in enumerate(document.tables):
        print(f"\n--- Table {index} ---")
        print(type(table))
        print(table.export_to_dataframe())

    print("\n=== DETAILED TABLE EXPLORATION ===")
    for item, level in document.iterate_items():
        if item.label.value == "table":
            print("TYPE:", type(item))
            print("LABEL:", item.label)
            print("DIR:")
            print([name for name in dir(item) if not name.startswith("_")])

            print("\nOBJECT:")
            print(item)

            print("\nPROVENANCE:")
            print(item.prov)

            print("\nTABLE DATA:")
            print(item.data)

    print("\n=== DOCUMENT ITEMS ===")
    for index, item in enumerate(document.iterate_items()):
        print(f"\n--- Item {index} ---")
        print("Type:", type(item))
        print("Item:", item)


if __name__ == "__main__":
    main()