from pathlib import Path
from starlette.applications import Starlette
from starlette.responses import FileResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from app import seed
from app.routers.核心 import 路由表

_STATIC = Path(__file__).resolve().parent / "static"


async def 登录页(request):
    return FileResponse(_STATIC / "login.html")


async def 首页(request):
    return FileResponse(_STATIC / "index.html")


async def 静态页(request):
    name = request.path_params["name"]
    p = _STATIC / name
    if not p.is_file():
        return RedirectResponse("/")
    return FileResponse(p)


async def 启动():
    seed.初始化库()


app = Starlette(
    debug=False,
    routes=[
        *路由表,
        Route("/login", 登录页),
        Route("/", 首页),
        Mount("/assets", StaticFiles(directory=str(_STATIC)), name="assets"),
        Route("/{name:path}", 静态页),
    ],
    on_startup=[启动],
)
