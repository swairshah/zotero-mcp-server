from pathlib import Path

import fastapi
import fastapi.staticfiles
import modal

app = modal.App("pdf-to-md-server")

web_app = fastapi.FastAPI()

@web_app.post("/parse")
async def parse(request: fastapi.Request):
    parse_pdf = modal.Function.from_name(
        "pdf-to-md-jobs", "parse_pdf"
    )

    form = await request.form()
    paper = await form["paper"].read()  # type: ignore
    call = parse_pdf.spawn(paper)

    return {"call_id": call.object_id}

@web_app.get("/result/{call_id}")
async def poll_results(call_id: str):
    function_call = modal.functions.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except TimeoutError:
        return fastapi.responses.JSONResponse(content="", status_code=202)

    return result

image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]==0.115.4"
)

@app.function(image=image)
@modal.asgi_app()
def fastapi_app():
    return web_app
