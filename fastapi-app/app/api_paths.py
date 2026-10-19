"""API 路径契约。

上传路由必须在请求体解析前进入并发保护，因此中间件只能根据请求路径判断。
路由声明和中间件共同引用这里的定义，避免路径变更后静默失去保护。
"""

DOCUMENTS_PREFIX = "/documents"
DOCUMENT_UPLOAD_ROUTE = ""
DOCUMENT_LIST_ROUTE = ""
DOCUMENT_ITEM_ROUTE = "/{doc_id}"
DOCUMENT_PREVIEW_ROUTE = "/{doc_id}/preview"
DOCUMENT_DOWNLOAD_ROUTE = "/{doc_id}/download"
DOCUMENT_OCR_ROUTE = "/{doc_id}/ocr"
DOCUMENT_OCR_STATUS_ROUTE = "/{doc_id}/ocr-status"
DOCUMENT_PROCESSING_STATUS_ROUTE = "/{doc_id}/processing-status"
DOCUMENT_RECYCLE_ROUTE = "/recycle-bin"
DOCUMENT_RESTORE_ROUTE = "/recycle-bin/{doc_id}/restore"
DOCUMENT_PURGE_ROUTE = "/recycle-bin/{doc_id}"

FILES_PREFIX = "/files"
FILE_UPLOAD_ROUTE = "/upload"

DOCUMENT_UPLOAD_PATH = f"{DOCUMENTS_PREFIX}{DOCUMENT_UPLOAD_ROUTE}"
FILE_UPLOAD_PATH = f"{FILES_PREFIX}{FILE_UPLOAD_ROUTE}"

UPLOAD_PATHS = frozenset({
    DOCUMENT_UPLOAD_PATH,
    FILE_UPLOAD_PATH,
})
