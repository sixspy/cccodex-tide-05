from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from pathlib import Path
from app.services import 目录, 装载, 关窗, 贯验, 夹具, 统计, 说明


async def api_概览(request: Request):
    return JSONResponse(目录.概览())


async def api_仓情(request: Request):
    return JSONResponse(说明.仓情())


async def api_窗规_get(request: Request):
    return JSONResponse(目录.窗规())


async def api_窗规_post(request: Request):
    body = await request.json()
    return JSONResponse(目录.改窗规(body))


async def api_网点(request: Request):
    return JSONResponse(目录.网点列表())


async def api_观测(request: Request):
    return JSONResponse(目录.观测列表())


async def api_缓冲(request: Request):
    return JSONResponse(目录.缓冲列表())


async def api_切片(request: Request):
    return JSONResponse(目录.切片列表())


async def api_迟到(request: Request):
    return JSONResponse(目录.迟到列表())


async def api_贯验列表(request: Request):
    return JSONResponse(目录.贯验列表())


async def api_夹具(request: Request):
    return JSONResponse(夹具.列表())


async def api_装载(request: Request):
    body = await request.json()
    return JSONResponse(装载.装一批(body))


async def api_夹具装载(request: Request):
    名 = request.path_params["name"]
    try:
        return JSONResponse(装载.装一批(夹具.读取(名)))
    except FileNotFoundError:
        return JSONResponse({"错误": 名}, status_code=404)


async def api_关窗(request: Request):
    return JSONResponse(关窗.关当前窗())


async def api_贯验(request: Request):
    return JSONResponse(贯验.跑一次())


async def api_统计观测(request: Request):
    return JSONResponse(统计.观测命运())


async def api_统计缓冲(request: Request):
    return JSONResponse(统计.缓冲命运())


async def api_空桩(request: Request):
    root = Path(__file__).resolve().parents[1] / "modules"
    out = []
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if p.is_dir() and p.name != "__pycache__" and (p / "__init__.py").is_file():
                out.append(p.name)
    return JSONResponse({"空桩": out, "条数": len(out)})


路由表 = [
    Route("/api/概览", api_概览),
    Route("/api/仓情", api_仓情),
    Route("/api/窗规", api_窗规_get, methods=["GET"]),
    Route("/api/窗规", api_窗规_post, methods=["POST"]),
    Route("/api/网点源", api_网点),
    Route("/api/观测点", api_观测),
    Route("/api/入窗缓冲", api_缓冲),
    Route("/api/窗切片账", api_切片),
    Route("/api/迟到匣", api_迟到),
    Route("/api/窗贯验", api_贯验列表),
    Route("/api/夹具", api_夹具),
    Route("/api/观测点/装载", api_装载, methods=["POST"]),
    Route("/api/观测点/夹具/{name}", api_夹具装载, methods=["POST"]),
    Route("/api/关窗/跑", api_关窗, methods=["POST"]),
    Route("/api/窗贯验/跑", api_贯验, methods=["POST"]),
    Route("/api/统计/观测命运", api_统计观测),
    Route("/api/统计/缓冲命运", api_统计缓冲),
    Route("/api/空桩", api_空桩),
]
