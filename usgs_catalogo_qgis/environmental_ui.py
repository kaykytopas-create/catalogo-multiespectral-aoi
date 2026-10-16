# SPDX-License-Identifier: GPL-2.0-or-later
"""Independent consultation tab. Workers never access live project layers."""
import math
import os
import re
import time
from qgis.PyQt.QtCore import QThread, QTimer, QUrl, QStandardPaths, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,
    QLineEdit,QPushButton,QCheckBox,QTextBrowser,QProgressBar,QFileDialog,QMessageBox,QGroupBox)
from qgis.core import (QgsProject,QgsVectorLayer,QgsWkbTypes,QgsGeometry,QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,QgsDistanceArea,QgsSettings,QgsFeatureRequest)
from .environmental import UFS, car_code, judicial_number, run_assessment, LABELS, STATUSES
from .environmental_http import ConsultationError
from .environmental_report import save_report, render_html, export_pdf


class AssessmentJob(QThread):
    result=pyqtSignal(object)
    failed=pyqtSignal(str)
    status=pyqtSignal(str,str)
    def __init__(self,context,folder,parent=None):
        super().__init__(parent);self.context,self.folder=context,folder;self.stopping=False
    def cancel(self):self.stopping=True
    def run(self):
        try:
            report=run_assessment(self.context,self.status.emit,lambda:self.stopping)
            paths=save_report(report,self.folder)
            self.result.emit({'report':report,'paths':paths})
        except Exception as exc:self.failed.emit(str(exc))


class EnvironmentalTab(QWidget):
    def __init__(self,iface,parent=None):
        super().__init__(parent);self.iface=iface;self.job=None;self.last=None;self.elapsed_start=0
        layout=QVBoxLayout(self)
        intro=QLabel('Consulta ambiental e fundiária por limite do imóvel. Busca pública com orçamento de até 5 minutos, sem baixar imagens. Ao final, entrega o relatório breve e informa as pendências.');intro.setWordWrap(True);layout.addWidget(intro)
        form=QFormLayout();self.parcel=QComboBox();self.refresh=QPushButton('Atualizar camadas')
        row=QHBoxLayout();row.addWidget(self.parcel,1);row.addWidget(self.refresh);form.addRow('Limite do imóvel',row)
        self.selected=QCheckBox('Usar somente feições selecionadas (se desmarcado, a camada deve ter um único imóvel)');form.addRow('',self.selected)
        self.name=QLineEdit();self.name.setPlaceholderText('Nome para o relatório (opcional)');form.addRow('Identificação',self.name)
        self.uf=QComboBox();self.uf.addItems(sorted(UFS));self.uf.setCurrentText('PA');form.addRow('UF da área',self.uf)
        self.car=QLineEdit();self.car.setPlaceholderText('PA-1500000-32 caracteres do recibo federal (opcional)');form.addRow('Recibo CAR',self.car)
        layout.addLayout(form)
        detail=QGroupBox('Consulta judicial por número CNJ (opcional)');details=QFormLayout(detail)
        self.numbers=QLineEdit();self.numbers.setPlaceholderText('Números CNJ separados por ponto e vírgula; máximo 20');details.addRow('Processos conhecidos',self.numbers)
        self.key=QLineEdit();self.key.setPlaceholderText('Busca automática na documentação CNJ; informe a chave pública se o portal não responder');details.addRow('Chave pública DataJud',self.key)
        note=QLabel('O DataJud consulta os números informados; não localiza todos os processos por polígono, nome ou CPF. Fundiário online: recorte Pará do ITERPA, incluindo camadas federais. <a href="https://datajud-wiki.cnj.jus.br/api-publica/acesso/">Acesso e condições CNJ</a>.');note.setWordWrap(True);note.setOpenExternalLinks(True);details.addRow(note);layout.addWidget(detail)
        row=QHBoxLayout();self.run=QPushButton('Consultar e gerar relatório · até 5 min');self.stop=QPushButton('Cancelar e preservar resultados');self.stop.setEnabled(False)
        row.addWidget(self.run);row.addWidget(self.stop);layout.addLayout(row)
        self.progress=QProgressBar();self.progress.setRange(0,300);self.progress.setValue(0);layout.addWidget(self.progress)
        self.status=QLabel('Selecione o limite. CAR ativo não equivale a regularidade ambiental, e registros fundiários não comprovam domínio.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.browser=QTextBrowser();self.browser.setOpenExternalLinks(True);layout.addWidget(self.browser,1)
        row=QHBoxLayout();self.output=QPushButton('Pasta dos relatórios');self.open=QPushButton('Abrir último relatório');self.pdf=QPushButton('Exportar PDF breve');self.open.setEnabled(False);self.pdf.setEnabled(False)
        row.addWidget(self.output);row.addWidget(self.open);row.addWidget(self.pdf);layout.addLayout(row)
        documents=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or os.path.expanduser('~')
        self.folder=str(QgsSettings().value('catalogo_multiespectral/consulta_folder',os.path.join(documents,'Catalogo_Multiespectral_Relatorios')))
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.tick)
        self.refresh.clicked.connect(self.refresh_layers);self.run.clicked.connect(self.start);self.stop.clicked.connect(self.cancel)
        self.output.clicked.connect(self.choose_folder);self.open.clicked.connect(self.open_report);self.pdf.clicked.connect(self.save_pdf)
        self.refresh_layers()

    def refresh_layers(self):
        selected=self.parcel.currentData();self.parcel.clear()
        for layer in sorted(QgsProject.instance().mapLayers().values(),key=lambda v:v.name().casefold()):
            if isinstance(layer,QgsVectorLayer) and layer.isValid() and layer.geometryType()==QgsWkbTypes.GeometryType.PolygonGeometry:
                self.parcel.addItem(layer.name(),layer.id())
        idx=self.parcel.findData(selected)
        if idx>=0:self.parcel.setCurrentIndex(idx)

    def snapshot(self):
        from .prodes_geometry import polygon_copy
        layer=QgsProject.instance().mapLayer(self.parcel.currentData())
        if not isinstance(layer,QgsVectorLayer) or not layer.isValid():raise ConsultationError('Selecione uma camada poligonal válida do imóvel.')
        if self.selected.isChecked() and layer.selectedFeatureCount()>1000:raise ConsultationError('Selecione somente as partes do imóvel, no máximo mil feições.')
        features=list(layer.getSelectedFeatures()) if self.selected.isChecked() else list(layer.getFeatures(QgsFeatureRequest().setLimit(2)))
        if not features:raise ConsultationError('Nenhuma feição no limite/seleção.')
        if not self.selected.isChecked() and len(features)!=1:raise ConsultationError('A camada contém vários imóveis: selecione as feições do imóvel e marque usar somente selecionadas.')
        if len(features)>1000:raise ConsultationError('Seleção muito grande para a consulta rápida de um imóvel.')
        parts=[polygon_copy(f.geometry(),'Limite')[0] for f in features]
        geom,_=polygon_copy(QgsGeometry.unaryUnion(parts),'União do limite')
        if not layer.crs().isValid():raise ConsultationError('A camada não tem um CRS válido.')
        crs=QgsCoordinateReferenceSystem('EPSG:4326')
        geom.transform(QgsCoordinateTransform(layer.crs(),crs,QgsProject.instance()))
        geom,_=polygon_copy(geom,'Limite em longitude/latitude')
        box=geom.boundingBox();rect=[box.xMinimum(),box.yMinimum(),box.xMaximum(),box.yMaximum()]
        if not all(math.isfinite(v) for v in rect) or not -180<=rect[0]<rect[2]<=180 or not -90<=rect[1]<rect[3]<=90:
            raise ConsultationError('Coordenadas do limite inválidas após reprojeção; confira o CRS da camada.')
        measure=QgsDistanceArea();measure.setSourceCrs(crs,QgsProject.instance().transformContext());measure.setEllipsoid('WGS84');area=measure.measureArea(geom)/10000
        if area>1000000:raise ConsultationError('Área acima de um milhão de hectares: divida a consulta para manter o tempo e o volume de dados limitados.')
        receipt=car_code(self.car.text())
        if receipt and receipt[:2]!=self.uf.currentText():raise ConsultationError('UF selecionada difere da UF do recibo CAR.')
        numbers=[n.strip() for n in re.split(r'[;\n,]+',self.numbers.text()) if n.strip()]
        if len(numbers)>20:raise ConsultationError('Informe no máximo vinte processos por consulta.')
        for number in numbers:judicial_number(number)
        return {'wkt':geom.asWkt(),'rect':rect,'parcel_area_ha':area,'uf':self.uf.currentText(),'car':receipt,
                'name':self.name.text().strip() or layer.name(),'judicial_numbers':numbers,'datajud_key':self.key.text().strip()}

    def busy(self,value):
        for widget in (self.parcel,self.refresh,self.selected,self.name,self.uf,self.car,self.numbers,self.key,self.run,self.output):widget.setEnabled(not value)
        self.stop.setEnabled(value)
        self.open.setEnabled(not value and self.last is not None);self.pdf.setEnabled(not value and self.last is not None)

    def start(self):
        if self.job:return
        try:context=self.snapshot()
        except Exception as exc:QMessageBox.warning(self,'Consulta ambiental e fundiária',str(exc));return
        self.elapsed_start=time.monotonic();self.busy(True);self.progress.setValue(0);self.timer.start()
        self.browser.setHtml('<p>Consultando CAR, embargos, processos vinculados e bases fundiárias em paralelo…</p>')
        self.job=AssessmentJob(context,self.folder,self);self.job.status.connect(self.source_status);self.job.result.connect(self.completed);self.job.failed.connect(self.failed);self.job.finished.connect(self.finished);self.job.start()

    def source_status(self,source,status):
        self.status.setText(LABELS[source]+': '+STATUSES[status]+'. '+self.time_text())

    def time_text(self):
        elapsed=min(300,int(time.monotonic()-self.elapsed_start));remaining=max(0,300-elapsed)
        return '{:02d}:{:02d} decorridos · orçamento restante {:02d}:{:02d}'.format(elapsed//60,elapsed%60,remaining//60,remaining%60)

    def tick(self):
        self.progress.setValue(min(300,int(time.monotonic()-self.elapsed_start)))
        self.status.setText(self.time_text()+' · servidores podem encerrar com resultado parcial.')
        if time.monotonic()-self.elapsed_start>=300 and self.job:self.job.cancel()

    def cancel(self):
        if self.job:self.job.cancel();self.status.setText('Cancelando consultas; preservando o que já foi recebido…')

    def completed(self,value):
        self.last=value;self.browser.setHtml(render_html(value['report']))
        self.status.setText('Relatório salvo · {:.1f} s. Resultados completos e pendentes estão identificados. {}'.format(value['report']['elapsed_seconds'],value['paths']['html']))
        self.progress.setValue(min(300,int(value['report']['elapsed_seconds'])))

    def failed(self,message):self.status.setText('Consulta não concluída: '+message)

    def finished(self):
        self.timer.stop();job=self.job;self.job=None;self.busy(False)
        if job:job.deleteLater()

    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Pasta para relatórios ambientais e fundiários',self.folder)
        if folder:self.folder=folder;QgsSettings().setValue('catalogo_multiespectral/consulta_folder',folder)

    def open_report(self):
        if self.last:QDesktopServices.openUrl(QUrl.fromLocalFile(self.last['paths']['html']))

    def save_pdf(self):
        if not self.last:return
        path,_=QFileDialog.getSaveFileName(self,'Exportar relatório breve em PDF',self.last['paths']['html'].rsplit('.',1)[0]+'.pdf','PDF (*.pdf)')
        if not path:return
        if not path.lower().endswith('.pdf'):path+='.pdf'
        try:export_pdf(render_html(self.last['report']),path);self.status.setText('PDF salvo: '+path)
        except Exception as exc:QMessageBox.warning(self,'PDF',str(exc))
