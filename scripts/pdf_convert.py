import argparse
import sys
import time
from pathlib import Path
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered

def main():
    start_time = time.time()
    
    parser = argparse.ArgumentParser(description='Convert PDF files to text using marker')
    parser.add_argument('pdf_path', type=str, help='Path to the PDF file')
    parser.add_argument('--output', '-o', type=str, help='Output file path (optional, defaults to stdout)')
    parser.add_argument('--save-images', '-i', action='store_true', help='Save extracted images')
    parser.add_argument('--image-dir', type=str, default='images', help='Directory to save images (default: images/)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Suppress timing information')

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF file '{pdf_path}' does not exist", file=sys.stderr)
        sys.exit(1)

    converter = PdfConverter(
        artifact_dict=create_model_dict(),
    )

    convert_start = time.time()
    rendered = converter(str(pdf_path))
    convert_time = time.time() - convert_start

    extract_start = time.time()
    text, _, images = text_from_rendered(rendered)
    extract_time = time.time() - extract_start

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(text)
    else:
        print(text)

    # save images if requested
    if args.save_images and images:
        image_dir = Path(args.image_dir)
        image_dir.mkdir(exist_ok=True)
        for idx, img in enumerate(images):
            img_path = image_dir / f"image_{idx}.png"
            img.save(img_path)
            print(f"Saved image to {img_path}", file=sys.stderr)

    total_time = time.time() - start_time
    
    if not args.quiet:
        print("\nTiming Information:", file=sys.stderr)
        print(f"PDF Conversion: {convert_time:.2f}s", file=sys.stderr)
        print(f"Text Extraction: {extract_time:.2f}s", file=sys.stderr)
        print(f"Total Time: {total_time:.2f}s", file=sys.stderr)

if __name__ == '__main__':
    main()
