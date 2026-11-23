"""API locale. Démarrage : uvicorn web.app:app --app-dir src --host 127.0.0.1."""
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from catalog import DossierNotFoundError
from web.service import WebService

MAX_UPLOAD = 20 * 1024 * 1024


class SearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=5)

    @field_validator('question')
    @classmethod
    def question_not_blank(cls, value):
        if not value.strip():
            raise ValueError('La question est vide.')
        return value


def create_app(factory=WebService):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = factory()
        try:
            yield
        finally:
            app.state.service.close()

    app = FastAPI(title='SPOC · Recherche documentaire', version='0.1.0', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def local_requests(request, call_next):
        origin = request.headers.get('origin')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and origin not in {
            'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000',
        }:
            return JSONResponse(status_code=403, content={'detail': 'Origine non autorisée.'})
        if request.url.path.endswith('/imports'):
            size = request.headers.get('content-length', '')
            if not size.isdigit() or int(size) > MAX_UPLOAD + 1024 * 1024:
                return JSONResponse(status_code=413, content={'detail': 'PDF limité à 20 Mo ; taille de requête requise.'})
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(DossierNotFoundError)
    async def unknown_dossier(request, exc):
        return JSONResponse(status_code=404, content={'detail': 'Dossier introuvable.'})

    @app.exception_handler(FileNotFoundError)
    async def unknown_file(request, exc):
        return JSONResponse(status_code=404, content={'detail': 'Source introuvable dans ce dossier.'})

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        return JSONResponse(status_code=422, content={'detail': 'Données invalides : vérifiez la question, le fichier et les paramètres.'})

    @app.exception_handler(ValueError)
    async def invalid_operation(request, exc):
        logging.getLogger(__name__).warning('Opération refusée : %s', exc)
        return JSONResponse(status_code=400, content={'detail': 'Opération impossible. Vérifiez les données et la configuration du serveur.'})

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        logging.getLogger(__name__).exception('Erreur API', exc_info=exc)
        return JSONResponse(status_code=500, content={'detail': 'Le serveur a rencontré une erreur. Consultez son journal.'})

    @app.get('/api/health')
    def health(request: Request):
        config = request.app.state.service.index_config
        return {'status': 'ok', 'prototype': True,
                'retrieval': {'model': config.embedding.model_name,
                              'preparation': 'contexte_coherent' if config.coherent else 'historique'}}

    @app.get('/api/dossiers')
    def dossiers(request: Request):
        return request.app.state.service.dossiers()

    @app.get('/api/dossiers/{dossier_id}/documents')
    def documents(dossier_id: str, request: Request):
        return request.app.state.service.documents(dossier_id)

    @app.post('/api/dossiers/{dossier_id}/search')
    def search(dossier_id: str, body: SearchRequest, request: Request):
        return {'results': request.app.state.service.search(dossier_id, body.question, body.top_k)}

    @app.post('/api/dossiers/{dossier_id}/imports', status_code=202)
    async def upload(dossier_id: str, request: Request, response: Response, file: UploadFile = File(...)):
        try:
            content = await file.read(MAX_UPLOAD + 1)
            name = Path((file.filename or '').replace('\\', '/')).name
            name = ''.join(c for c in name if c.isprintable())[:160]
            if not name.lower().endswith('.pdf') or not content.startswith(b'%PDF-'):
                raise HTTPException(415, 'Sélectionnez un véritable fichier PDF.')
            if len(content) > MAX_UPLOAD:
                raise HTTPException(413, 'Le PDF dépasse la limite de 20 Mo.')
            # L’écriture et l’enregistrement ne bloquent pas la boucle HTTP.
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(request.app.state.service.submit, dossier_id, name, content)
            if result['duplicate']:
                response.status_code = 200
            return result
        finally:
            await file.close()

    @app.get('/api/jobs/{job_id}')
    def job(job_id: str, request: Request):
        service = request.app.state.service
        result = service.jobs.get(job_id)
        if result is None:
            raise HTTPException(404, 'Traitement introuvable.')
        service.require_dossier(result['dossier_id'])
        return service.jobs.public(result)

    @app.get('/api/dossiers/{dossier_id}/documents/{document_id}/source')
    def source(dossier_id: str, document_id: str, request: Request):
        result = request.app.state.service.source(dossier_id, document_id)
        if result['kind'] == 'pdf':
            return {'kind': 'pdf', 'name': result['name']}
        return result

    @app.get('/api/dossiers/{dossier_id}/documents/{document_id}/file')
    def file(dossier_id: str, document_id: str, request: Request):
        result = request.app.state.service.source(dossier_id, document_id)
        if result['kind'] != 'pdf':
            raise HTTPException(415, 'Cette source est un document texte.')
        return FileResponse(result['path'], media_type='application/pdf', filename=result['name'], content_disposition_type='inline')

    return app


app = create_app()
