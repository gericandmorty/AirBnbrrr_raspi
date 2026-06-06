from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pathlib import Path
import re
from services.auth import get_admin_from_token

router = APIRouter()

TEMPLATES_DIR = Path("templates/pages")


def _read_template(filename: str) -> str:
    p = TEMPLATES_DIR / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    content = p.read_text(encoding="utf-8")

    # Simple recursive parser to resolve <!-- INCLUDE filename.html --> comments
    def resolve_includes(text: str) -> str:
        pattern = r"<!--\s*INCLUDE\s+([A-Za-z0-9_-]+\.html)\s*-->"
        def replace(match):
            inc_file = match.group(1)
            inc_path = TEMPLATES_DIR / inc_file
            if inc_path.exists():
                return resolve_includes(inc_path.read_text(encoding="utf-8"))
            return f"<!-- Include error: {inc_file} not found -->"
        return re.sub(pattern, replace, text)

    resolved = resolve_includes(content)
    if 'rel="icon"' not in resolved and 'rel="shortcut icon"' not in resolved:
        favicon_html = '\n    <link rel="icon" type="image/png" href="/assets/xd/logo.png?v=3">\n    <link rel="shortcut icon" type="image/png" href="/assets/xd/logo.png?v=3">'
        if "<head>" in resolved:
            resolved = resolved.replace("<head>", f"<head>{favicon_html}", 1)
        elif "<HEAD>" in resolved:
            resolved = resolved.replace("<HEAD>", f"<HEAD>{favicon_html}", 1)
            
    return resolved


@router.get("/pages", response_class=HTMLResponse)
def pages_index(request: Request):
    token = request.cookies.get("admin_session")
    if not get_admin_from_token(token):
        return RedirectResponse(url="/pages/login", status_code=303)
    return HTMLResponse(_read_template("index.html"))


@router.get("/pages/{name}", response_class=HTMLResponse)
def page(name: str, request: Request):
    # Restrict page name to safe characters to avoid path traversal
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise HTTPException(status_code=400, detail="Invalid page name")
    
    # Check session
    token = request.cookies.get("admin_session")
    is_authenticated = get_admin_from_token(token) is not None

    if name == "login":
        # If already logged in, skip login page and go straight to the Control Panel
        if is_authenticated:
            return RedirectResponse(url="/", status_code=303)
    else:
        # Enforce authentication for all other pages
        if not is_authenticated:
            return RedirectResponse(url="/pages/login", status_code=303)
            
    return HTMLResponse(_read_template(f"{name}.html"))
