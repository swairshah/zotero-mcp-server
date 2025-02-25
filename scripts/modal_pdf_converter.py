import modal
from pathlib import Path

app = modal.App("pdf-to-md-jobs")

inference_image = modal.Image.debian_slim(python_version="3.12").pip_install(
	"marker-pdf>=1.5.5"
)

def setup():
    import warnings

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    with (
        warnings.catch_warnings()
    ):  # filter noisy warnings from GOT modeling code
        warnings.simplefilter("ignore")
        
        converter = PdfConverter(
			artifact_dict=create_model_dict(),
		)

    return converter

@app.function(
    gpu="l40s",
    retries=3,
    # volumes={MODEL_CACHE_PATH: model_cache},
    image=inference_image,
)
def parse_pdf(pdf: bytes) -> str:
    from tempfile import NamedTemporaryFile
    from marker.output import text_from_rendered
    
    converter = setup()
    
    with NamedTemporaryFile(delete=False, mode="wb+") as temp_file:
        temp_file.write(pdf)
        rendered = converter(str(temp_file.name))
        text, _, images = text_from_rendered(rendered)

    print("Result: ", text)
    return text

@app.local_entrypoint()
def main(local_filename: str = None):
    from pathlib import Path

    import requests

    local_filename = Path(local_filename)

    if local_filename.exists():
        pdf_file = local_filename.read_bytes()
        print(f"parsing {local_filename}.")
    print(parse_pdf.remote(pdf_file))


