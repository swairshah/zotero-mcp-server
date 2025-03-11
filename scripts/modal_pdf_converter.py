import modal
import os
from pathlib import Path

app = modal.App("pdf-to-md-jobs")

model_volume = modal.Volume.from_name("models-volume", create_if_missing=True)
VOLUME_PATH = "/root/.cache"

inference_image = modal.Image.debian_slim(python_version="3.12").pip_install(
	"marker-pdf>=1.5.5", 
	"platformdirs"
)

def setup():
    import warnings
    import os
    from pathlib import Path
    import shutil

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from platformdirs import user_cache_dir

    with warnings.catch_warnings():  
        warnings.simplefilter("ignore")
        
        converter = PdfConverter(
            artifact_dict=create_model_dict(),
        )

        model_volume.commit()

    return converter

@app.function(
    gpu="l40s",
    retries=3,
    volumes={VOLUME_PATH: model_volume},
    image=inference_image,
)
def parse_pdf(pdf: bytes) -> str:
    import os
    from tempfile import NamedTemporaryFile
    from marker.output import text_from_rendered
   
    converter = setup()

    with NamedTemporaryFile(delete=False, mode="wb+") as temp_file:
        temp_file.write(pdf)
        rendered = converter(str(temp_file.name))
        text, _, images = text_from_rendered(rendered)

    # print("Result: ", text)
    return text

@app.local_entrypoint()
def main(local_filename: str = None):
    from pathlib import Path

    local_filename = Path(local_filename)

    if local_filename.exists():
        pdf_file = local_filename.read_bytes()
        print(f"Parsing {local_filename}...")
        print(parse_pdf.remote(pdf_file))
    else:
        print(f"Error: File '{local_filename}' does not exist")

