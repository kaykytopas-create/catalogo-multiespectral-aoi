# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only public requests, bounded by a shared wall-clock budget."""
import json
import re
import time
import threading
from urllib.parse import urlparse, urlencode


class ConsultationError(Exception):
    pass


class BudgetExpired(ConsultationError):
    pass


class ConsultationCancelled(ConsultationError):
    pass


class TemporarySourceError(ConsultationError):
    pass


class Budget:
    def __init__(self, seconds=295, cancelled=lambda: False, clock=time.monotonic):
        self.clock, self.cancelled = clock, cancelled
        self.started = clock()
        self.deadline = self.started + min(295, max(0, float(seconds)))

    def check(self):
        if self.cancelled():
            raise ConsultationCancelled('Consulta cancelada; resultados concluídos preservados.')
        if self.clock() >= self.deadline:
            raise BudgetExpired('Limite de tempo atingido; consulta parcial.')

    def remaining(self):
        return max(0, self.deadline - self.clock())


PATHS = {
    'datajud-wiki.cnj.jus.br': ('/api-publica/acesso/',),
    'geoserver.car.gov.br': ('/geoserver/sicar/wfs',),
    'geoservicos.inde.gov.br': ('/geoserver/ICMBio/ows',),
    'pamgia.ibama.gov.br': ('/server/rest/services/01_Publicacoes_Bases/adm_embargos_ibama_a/MapServer/0/query',),
    'monitoramento.semas.pa.gov.br': ('/ldi/pesquisa/pesquisarComCar',),
}


def allowed_url(url):
    try:
        p = urlparse(url)
        if p.scheme != 'https' or p.port not in (None, 443) or p.username or p.password or p.fragment:
            return False
        if p.hostname == 'arcgisportal.iterpa.pa.gov.br':
            return bool(re.fullmatch(r'/server/rest/services/SICARF/acervoFundiarioMapserver/MapServer/(?:63|64|72|73|93|97|98)/query',p.path))
        if p.hostname == 'api-publica.datajud.cnj.jus.br':
            return bool(re.fullmatch(r'/api_publica_(?:trf[1-6]|tj[a-z]{2,4}|trt(?:[1-9]|1[0-9]|2[0-4]))/_search', p.path)) and not p.query
        return p.path in PATHS.get(p.hostname, ())
    except ValueError:
        return False


class PublicHttp:
    def __init__(self, budget, timeout=25, max_bytes=8 * 1024 * 1024):
        self.budget, self.timeout, self.max_bytes = budget, timeout, max_bytes
        self.land_slots = threading.BoundedSemaphore(2)

    def __call__(self, url, payload=None, headers=None):
        limited = urlparse(url).hostname == 'arcgisportal.iterpa.pa.gov.br'
        if limited:
            while not self.land_slots.acquire(timeout=.1):
                self.budget.check()
        try:
            return self._with_retry(url,payload,headers)
        finally:
            if limited:
                self.land_slots.release()

    def _with_retry(self, url, payload=None, headers=None):
        for attempt in range(2):
            try:
                return self._request(url, payload, headers)
            except TemporarySourceError:
                # Retry once, only while the original global budget permits it.
                if attempt or self.budget.remaining() < self.timeout + 1:
                    raise
                retry_at = self.budget.clock() + 1
                while self.budget.clock() < retry_at:
                    self.budget.check()
                    time.sleep(.05)

    def _request(self, url, payload=None, headers=None):
        self.budget.check()
        if not allowed_url(url):
            raise ConsultationError('Endereço fora das fontes públicas autorizadas.')
        host = urlparse(url).hostname
        if payload is not None and host not in ('api-publica.datajud.cnj.jus.br','arcgisportal.iterpa.pa.gov.br'):
            raise ConsultationError('Esta fonte admite apenas leitura por GET.')
        if headers and urlparse(url).hostname != 'api-publica.datajud.cnj.jus.br':
            raise ConsultationError('Credencial não permitida nesta fonte pública.')
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtCore import QEventLoop, QTimer, QUrl, QByteArray
        from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setRawHeader(b'User-Agent', b'QGIS-Catalogo-Multiespectral/3.5 public-read-only')
        request.setRawHeader(b'Accept', b'application/json, application/geo+json, text/html')
        for key, value in (headers or {}).items():
            if key != 'Authorization' or not re.fullmatch(r'APIKey [A-Za-z0-9+/=_-]+', value):
                raise ConsultationError('Cabeçalho de autenticação inválido.')
            request.setRawHeader(key.encode(), value.encode())
        # Create the event dispatcher BEFORE the manager starts network timers.
        # Python pool threads are adopted by Qt and initially have no dispatcher.
        loop, timer, chunks, reasons = QEventLoop(), QTimer(), [], []
        # instance() supplies a manager in the calling thread, using QGIS proxy settings.
        manager = QgsNetworkAccessManager.instance()
        if payload is None:
            reply = manager.get(request)
        else:
            form = host == 'arcgisportal.iterpa.pa.gov.br'
            request.setRawHeader(b'Content-Type', b'application/x-www-form-urlencoded' if form else b'application/json')
            reply = manager.post(request, QByteArray((urlencode(payload) if form else json.dumps(payload)).encode()))
        started = self.budget.clock()
        received = [0]
        def read():
            if hasattr(reply, "isOpen") and not reply.isOpen():
                return
            value = bytes(reply.readAll())
            received[0] += len(value)
            if received[0] > self.max_bytes:
                reasons.append('Resposta pública excedeu 8 MB; reduza a área consultada.')
                reply.abort()
            else:
                chunks.append(value)
        def tick():
            try:
                self.budget.check()
                if self.budget.clock() - started >= self.timeout:
                    raise TemporarySourceError('Fonte não respondeu no prazo desta requisição.')
            except ConsultationError as exc:
                reasons.append(exc)
                reply.abort()
        reply.readyRead.connect(read)
        reply.finished.connect(loop.quit)
        timer.timeout.connect(tick)
        timer.start(100)
        try:
            if not reply.isFinished():
                loop.exec()
            timer.stop()
            if not reasons:
                read()
            self.budget.check()
            if reasons:
                reason = reasons[0]
                raise reason if isinstance(reason, Exception) else ConsultationError(reason)
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NetworkError.NoError or status is None or not 200 <= int(status) < 300:
                if status is None or int(status) in (500,502,503,504):
                    raise TemporarySourceError('Falha temporária na fonte (HTTP {}).'.format(status))
                raise ConsultationError('Fonte indisponível (HTTP {}).'.format(status))
            return b''.join(chunks)
        finally:
            timer.stop()
            reply.readyRead.disconnect(read)
            reply.finished.disconnect(loop.quit)
            reply.deleteLater()
