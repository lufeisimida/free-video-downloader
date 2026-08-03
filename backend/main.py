import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from settings import load_backend_env
load_backend_env()

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from auth import get_current_user, sync_builtin_account
from downloader import VideoDownloader
from douyin import DouyinParser, is_douyin_url
from database import init_db, upsert_library_video
from local_media import (
    ALLOWED_EXTENSIONS,
    UPLOAD_DIR,
    build_local_video_info,
    is_local_media_url,
    read_metadata,
    resolve_local_path,
    write_metadata,
)


downloader = VideoDownloader()
douyin_parser = DouyinParser(download_dir=downloader.DOWNLOAD_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from learning_efficiency import init_efficiency_db
    init_efficiency_db()
    sync_builtin_account()
    from api_efficiency import resume_queued_pipelines
    from reminder_scheduler import reminder_scheduler_loop
    resume_queued_pipelines()
    reminder_task = asyncio.create_task(reminder_scheduler_loop())
    yield
    reminder_task.cancel()
    try:
        await reminder_task
    except asyncio.CancelledError:
        pass
    download_dir = downloader.DOWNLOAD_DIR
    if os.path.exists(download_dir):
        for f in os.listdir(download_dir):
            try:
                os.remove(os.path.join(download_dir, f))
            except OSError:
                pass


app = FastAPI(
    title="万能视频下载器 API",
    description="基于 yt-dlp 的万能视频下载服务，支持 1800+ 平台",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ParseRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_id: str = "bestvideo+bestaudio/best"


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "万能视频下载器服务运行中"}


@app.post("/api/parse")
async def parse_video(req: ParseRequest, user: dict = Depends(get_current_user)):
    """解析视频信息（抖音走专用模块，其他走 yt-dlp）。需登录。"""
    try:
        loop = asyncio.get_running_loop()
        if is_local_media_url(req.url):
            result = await loop.run_in_executor(None, build_local_video_info, req.url)
        elif is_douyin_url(req.url):
            result = await loop.run_in_executor(None, douyin_parser.parse, req.url)
        else:
            result = await loop.run_in_executor(None, downloader.parse_video, req.url)
        library_video = upsert_library_video(user["id"], req.url, result)
        result["library_id"] = library_video["id"]
        result["folder_id"] = library_video["folder_id"]
        return {"success": True, "data": result}
    except Exception as e:
        message = str(e)
        if "412" in message:
            message = (
                "解析被平台风控拦截（HTTP 412）。服务器 IP 常被 B 站等平台限制，"
                "请在「Cookie 配置」中填入浏览器导出的登录 Cookie 后重试。"
            )
        else:
            message = f"解析失败: {message}"
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": message,
        })


@app.post("/api/upload-local-video")
async def upload_local_video(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传本地视频，返回可复用现有解析流程的 local:// 标识。需登录。"""
    original_name = Path(file.filename or "video.mp4").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的本地视频格式: {extension or '未知'}",
        )

    max_bytes = int(os.getenv("MAX_LOCAL_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{extension}"
    stored_path = UPLOAD_DIR / stored_name
    total_size = 0

    try:
        with stored_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise HTTPException(status_code=413, detail="本地视频超过允许的最大上传大小")
                output.write(chunk)

        write_metadata(stored_name, {
            "original_name": original_name,
            "content_type": file.content_type or "application/octet-stream",
            "size": total_size,
        })
        return {
            "success": True,
            "data": {
                "url": f"local://{stored_name}",
                "filename": original_name,
                "size": total_size,
            },
        }
    except HTTPException:
        stored_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"本地视频上传失败: {exc}") from exc
    finally:
        await file.close()


@app.post("/api/download")
async def download_video(req: DownloadRequest, user: dict = Depends(get_current_user)):
    """服务端下载视频后提供文件下载（抖音走专用模块）。需登录。"""
    try:
        if is_local_media_url(req.url):
            filepath = resolve_local_path(req.url)
            if not filepath:
                raise HTTPException(status_code=404, detail="本地视频不存在")
            metadata = read_metadata(Path(filepath).name)
            return FileResponse(
                path=filepath,
                filename=metadata.get("original_name") or Path(filepath).name,
                media_type=metadata.get("content_type") or "application/octet-stream",
            )

        loop = asyncio.get_running_loop()
        if is_douyin_url(req.url):
            result = await loop.run_in_executor(None, douyin_parser.download, req.url)
        else:
            result = await loop.run_in_executor(
                None, downloader.download_video, req.url, req.format_id
            )
        filepath = result["filepath"]
        if not os.path.exists(filepath):
            raise HTTPException(status_code=500, detail="下载的文件不存在")

        return FileResponse(
            path=filepath,
            filename=result["filename"],
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": f"下载失败: {str(e)}"
        })


@app.post("/api/direct-url")
async def get_direct_url(req: DownloadRequest, user: dict = Depends(get_current_user)):
    """获取视频直链。需登录。"""
    try:
        if is_local_media_url(req.url):
            raise HTTPException(status_code=400, detail="本地视频不提供外部直链")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, downloader.get_direct_url, req.url, req.format_id
        )
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail={
            "success": False,
            "error": f"获取直链失败: {str(e)}"
        })


@app.get("/api/proxy/thumbnail")
async def proxy_thumbnail(
    url: str = Query(..., description="缩略图URL"),
    user: dict = Depends(get_current_user),
):
    """代理获取视频缩略图，绕过防盗链。需登录。"""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": url,
            })
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/jpeg")
            return StreamingResponse(
                iter([resp.content]),
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        raise HTTPException(status_code=502, detail="缩略图加载失败")


# 挂载功能模块路由
from api_summarize import router as summarize_router
from api_auth import router as auth_router
from api_payment import router as payment_router
from api_model_config import router as model_config_router
from api_cookie_config import router as cookie_config_router
from api_library import router as library_router
from api_efficiency import router as efficiency_router

app.include_router(summarize_router)
app.include_router(auth_router)
app.include_router(payment_router)
app.include_router(model_config_router)
app.include_router(cookie_config_router)
app.include_router(library_router)
app.include_router(efficiency_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
