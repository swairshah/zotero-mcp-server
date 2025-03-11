import modal
import os
from pathlib import Path
import fastapi
import fastapi.staticfiles

app = modal.App("pdf-to-md-jobs")
web_app = fastapi.FastAPI()

model_volume = modal.Volume.from_name("models-volume", create_if_missing=True)
VOLUME_PATH = "/root/.cache"

inference_image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "marker-pdf>=1.5.5", 
    "platformdirs",
    "fastapi[standard]==0.115.11",
)

@app.cls(
    gpu="l40s",
    volumes={VOLUME_PATH: model_volume},
    image=inference_image,
)
class Converter:
    @modal.enter()
    def setup(self):
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
        self.converter = converter

    @modal.method()
    def parse_pdf(self, pdf: bytes) -> str:
        import os
        from tempfile import NamedTemporaryFile
        from marker.output import text_from_rendered
        with NamedTemporaryFile(delete=False, mode="wb+") as temp_file:
            temp_file.write(pdf)
            rendered = self.converter(str(temp_file.name))
            text, _, images = text_from_rendered(rendered)

        return text

# def setup():
#     import warnings
#     import os
#     from pathlib import Path
#     import shutil
# 
#     from marker.converters.pdf import PdfConverter
#     from marker.models import create_model_dict
#     from platformdirs import user_cache_dir
# 
#     with warnings.catch_warnings():  
#         warnings.simplefilter("ignore")
#         
#         converter = PdfConverter(
#             artifact_dict=create_model_dict(),
#         )
# 
#         model_volume.commit()
# 
#     return converter
# 
# @app.function(
#     gpu="l40s",
#     retries=3,
#     volumes={VOLUME_PATH: model_volume},
#     image=inference_image,
# )
# def parse_pdf(pdf: bytes) -> str:
#     import os
#     from tempfile import NamedTemporaryFile
#     from marker.output import text_from_rendered
#    
#     converter = setup()
# 
#     with NamedTemporaryFile(delete=False, mode="wb+") as temp_file:
#         temp_file.write(pdf)
#         rendered = converter(str(temp_file.name))
#         text, _, images = text_from_rendered(rendered)
# 
#     # print("Result: ", text)
#     return text

@app.local_entrypoint()
def main(local_filename: str = None):
    from pathlib import Path

    local_filename = Path(local_filename)

    if local_filename.exists():
        pdf_file = local_filename.read_bytes()
        print(f"Parsing {local_filename}...")
        # print(parse_pdf.remote(pdf_file))
        converter = Converter()
        data = converter.parse_pdf.remote(pdf_file)
        print(data)

    else:
        print(f"Error: File '{local_filename}' does not exist")

converter = Converter()
@web_app.post("/parse")
async def parse(request: fastapi.Request):

    # parse_pdf = modal.Function.from_name(
    #     "pdf-to-md-jobs", "parse_pdf"
    # )
    # call = converter.parse_pdf(paper)

    form = await request.form()
    paper = await form["paper"].read()  # type: ignore

    # sync:
    return converter.parse_pdf.remote(paper)

    # async:
    # call = parse_pdf.spawn(paper)
    # return {"call_id": call.object_id}

@web_app.get("/result/{call_id}")
async def poll_results(call_id: str):
    function_call = modal.functions.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except TimeoutError:
        return fastapi.responses.JSONResponse(content="", status_code=202)

    return result

fastapi_image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]==0.115.11",
    "pydantic>=2.0.0"
)

@app.function(image=fastapi_image)
@modal.asgi_app()
def fastapi_app():
    return web_app
