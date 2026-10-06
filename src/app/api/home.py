from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["home"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return """
    <!doctype html>
    <html lang="pl">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>TaePlanDo</title>
      </head>
      <body>
        <main>
          <h1>TaePlanDo</h1>
          <p>Witaj w API TaePlanDo. Strona jest obecnie w przygotowaniu.</p>
        </main>
      </body>
    </html>
    """
