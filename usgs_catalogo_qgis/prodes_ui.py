# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Experimental PRODES intersection, assisted interpretation and export UI."""
import hashlib
import json
import os
import shutil
import csv
import tempfile
from datetime import datetime, timezone

from qgis.PyQt.QtCore import QDate, QThread, QUrl, QStandardPaths, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QTextDocument, QImage, QFont, QDesktopServices
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QDoubleSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget, QScrollArea)
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsDistanceArea, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsProject, QgsRasterLayer, QgsSettings,
    QgsVectorLayer, QgsWkbTypes, QgsFillSymbol, QgsVectorFileWriter,
    QgsMultiBandColorRenderer, QgsPrintLayout, QgsLayoutItemMap,
    QgsLayoutItemLabel, QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize,
    QgsLayoutExporter, QgsContrastEnhancement, QgsLayoutItemPicture, QgsRectangle, QgsUnitTypes)
from qgis.gui import QgsMapCanvas, QgsMapToolPan
from .prodes import TerraBrasilis, ProdesError, record, evaluate, report_html, annual_layers, ENDPOINT, RULE_VERSION
from .prodes_geometry import polygon_copy
from .prodes_auto import THRESHOLDS, metadata_for_layer, run_analysis
from .prodes_contestation import CONTEST_RULE_VERSION
from .prodes_autofetch import run_autofetch
from .prodes_agent import run_investigation, append_event
from .prodes_vision import LocalVision


class QueryJob(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, action, name=None, rect=None, parent=None):
        super().__init__(parent)
        self.action, self.name, self.rect = action, name, rect
        self.stopping = False

    def run(self):
        try:
            service = TerraBrasilis(cancelled=lambda: self.stopping)
            if self.action == "auto_features":
                offered = dict(annual_layers(service.layers()))
                if self.name not in offered:
                    raise ProdesError("Base anual escolhida não reconhecida no TerraBrasilis. Consulte e selecione uma base por bioma.")
                value = {"name": self.name, "data": service.features(self.name, self.rect, self.status.emit)}
            else:
                value = service.layers() if self.action == "layers" else service.features(self.name, self.rect, self.status.emit)
            if not self.stopping:
                self.result.emit(value)
        except Exception as exc:
            if not self.stopping:
                self.failed.emit(str(exc))


class AnalysisJob(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, payload, parent=None):
        super().__init__(parent)
        self.payload, self.stopping = payload, False

    def run(self):
        try:
            results = run_analysis(self.payload, self.status.emit, lambda: self.stopping)
            if not self.stopping:
                self.result.emit(results)
        except Exception as exc:
            if not self.stopping:
                self.failed.emit(str(exc))


class AutoEvidenceJob(AnalysisJob):
    def run(self):
        try:
            value = (run_investigation if self.payload.get("agent_enabled") else run_autofetch)(self.payload, self.status.emit, lambda: self.stopping)
            if not self.stopping:
                self.result.emit(value)
        except Exception as exc:
            if not self.stopping:
                self.failed.emit(str(exc))


class VisionJob(AnalysisJob):
    def run(self):
        try:
            client=LocalVision(lambda:self.stopping)
            if self.payload.get('list_models'):
                self.result.emit(client.models());return
            values=[]
            for index,row in enumerate(self.payload['rows']):
                if self.stopping:return
                self.status.emit('IA visual local: polígono {} de {}…'.format(index+1,len(self.payload['rows'])))
                cards=[v for v in self.payload['cards'] if v['polygon_index']==index]
                try:value=client.analyse(self.payload['model'],row,cards)
                except Exception as exc:
                    if self.stopping:return
                    value={'status':'Não executada: '+str(exc)}
                values.append(value)
            if not self.stopping:self.result.emit(values)
        except Exception as exc:
            if not self.stopping:self.failed.emit(str(exc))


def outline(layer, color, width):
    layer.renderer().setSymbol(QgsFillSymbol.createSimple({"color": "0,0,0,0",
        "outline_color": color, "outline_width": str(width), "style": "no"}))


class ProdesDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Catálogo Multiespectral 3.3 | Central de investigação ambiental")
        self.resize(1180, 740)
        self.work = tempfile.TemporaryDirectory(prefix="catalogo_prodes_")
        self.job = None
        self.after_job = None
        self.source = self.parcel = self.clipped = self.original = None
        self.rows = []
        self.analysis_geometries = []
        self.consolidated_geometries = []
        self.consolidated_preview = None
        self.map_rasters = []
        self.source_note = ""
        self.context = {}
        self.automatic_results = None
        self.analysis_payload = None
        self.map_evidence = []
        self.generated_maps = []
        self.maps_in_progress=False
        self.map_stopping=False
        root = QVBoxLayout(self)
        intro = QLabel("3.3 EXPERIMENTAL · Investigação automatizada: planejar, selecionar, comparar, argumentar e produzir cartas-imagem.\n"
            "Evidências rastreáveis e IA visual local opcional. Resultados para revisão técnica, sem homologação temática ou jurídica.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        source_tab = QWidget()
        inputs = QFormLayout(source_tab)
        self.name = QLineEdit()
        self.car = QLineEdit()
        self.reviewer = QLineEdit()
        self.property_box = QComboBox()
        self.selected = QCheckBox("Usar somente feições selecionadas (recomendado para vários imóveis)")
        self.selected.setChecked(True)
        self.car_boundary = QCheckBox("O limite é CAR: avaliar também a faixa interna de tolerância de 60 m")
        refresh = QPushButton("Atualizar camadas e imagens do projeto")
        refresh.clicked.connect(self.refresh_layers)
        inputs.addRow("Imóvel:", self.name)
        inputs.addRow("CAR (opcional):", self.car)
        inputs.addRow("Responsável pela revisão:", self.reviewer)
        inputs.addRow("Limite poligonal:", self.property_box)
        self.consolidated_box = QComboBox()
        self.consolidated_origin = QLineEdit()
        self.consolidated_origin.setPlaceholderText("Fonte, data da delimitação e documentos de uso histórico, se disponíveis")
        inputs.addRow("Área consolidada declarada (opcional):", self.consolidated_box)
        inputs.addRow("Origem/evidências da consolidada:", self.consolidated_origin)
        self.consolidated_technical = QCheckBox("Consolidada delimitada pelo técnico conforme art. 3º, IV, da Lei 12.651/2012")
        self.consolidated_technical.setToolTip("Reconhece a classificação técnica fornecida como evidência de entrada; não é uma homologação pelo plugin.")
        inputs.addRow(self.consolidated_technical)
        inputs.addRow(self.selected)
        inputs.addRow(self.car_boundary)
        inputs.addRow(refresh)
        self.history_start = QSpinBox()
        self.history_start.setRange(1982, QDate.currentDate().year()-2)
        self.history_start.setValue(1985)
        inputs.addRow("Início da pesquisa histórica:", self.history_start)
        self.agent_enabled=QCheckBox('Usar sistema de investigação adaptativa por polígono')
        self.agent_enabled.setChecked(True)
        inputs.addRow(self.agent_enabled)
        self.agent_offline=QCheckBox("Usar somente acervo local e PRODES em cache (sem consultas externas)")
        inputs.addRow(self.agent_offline)
        self.agent_profile=QComboBox()
        for title,key in [('Equilibrado','equilibrado'),('Rápido','rapido'),('Aprofundado','aprofundado')]:self.agent_profile.addItem(title,key)
        inputs.addRow('Profundidade da investigação:',self.agent_profile)
        self.scene_cloud_limit=QDoubleSpinBox();self.scene_cloud_limit.setRange(0,20);self.scene_cloud_limit.setDecimals(2);self.scene_cloud_limit.setValue(20)
        inputs.addRow('Máximo de nuvens da cena (%):',self.scene_cloud_limit)
        self.scene_cloud_strict=QCheckBox('Exigir menos que o valor informado (0 usa até 0; 20 usa menos de 20)');self.scene_cloud_strict.setChecked(True)
        inputs.addRow(self.scene_cloud_strict)
        self.scene_cloud_limit.valueChanged.connect(self.update_cloud_constraint)
        self.scene_cloud_limit.valueChanged.connect(self.invalidate)
        self.scene_cloud_strict.toggled.connect(self.invalidate)
        self.update_cloud_constraint(20)

        self.vision_enabled=QCheckBox('Interpretar cartas com IA visual local (Ollama instalado neste computador)')
        self.vision_enabled.setToolTip('Envia cartas reduzidas somente a 127.0.0.1:11434. Hipóteses visuais não alteram o parecer calculado. Não instala modelos automaticamente.')
        inputs.addRow(self.vision_enabled)
        self.vision_model=QComboBox();self.vision_model.setEditable(True)
        inputs.addRow('Modelo multimodal instalado:',self.vision_model)
        self.models_button=QPushButton('Verificar modelos na IA local')
        self.models_button.clicked.connect(self.discover_models)
        inputs.addRow(self.models_button)
        self.map_dpi=QSpinBox();self.map_dpi.setRange(150,450);self.map_dpi.setValue(300)
        inputs.addRow('Resolução de impressão (DPI):',self.map_dpi)
        inputs.addRow(QLabel('DPI melhora a impressão; não recupera detalhe ausente no sensor.'))
        self.auto_export=QCheckBox('Gerar relatório e pacote automaticamente no acervo ao concluir')
        self.auto_export.setChecked(True)
        inputs.addRow(self.auto_export)
        self.pipeline_button = QPushButton("Iniciar investigação: imóvel + consolidada → relatório")
        self.pipeline_button.setToolTip("Consulta PRODES, confirma a fonte oficial e busca imagens. Sem outra base selecionada, usa Amazônia florestal.")
        self.pipeline_button.clicked.connect(self.start_pipeline)
        inputs.addRow(self.pipeline_button)
        inputs.addRow(QLabel("Base automática padrão: Amazônia florestal. Para outro bioma, selecione sua base WFS abaixo."))
        self.service_layers = QComboBox()
        discovery = QPushButton("Consultar camadas do TerraBrasilis")
        discovery.clicked.connect(self.discover)
        inputs.addRow(discovery)
        inputs.addRow("Camada WFS:", self.service_layers)
        self.annual = QCheckBox("Confirmei nos metadados: incrementos de desmatamento/supressão por BIOMA")
        inputs.addRow(self.annual)
        self.year = QSpinBox()
        self.year.setRange(1988, QDate.currentDate().year())
        self.year.setValue(QDate.currentDate().year() - 1)
        inputs.addRow("Ano PRODES a analisar:", self.year)
        self.all_years = QCheckBox("Mostrar todos os anos encontrados no imóvel")
        self.all_years.setChecked(True)
        self.year.setEnabled(False)
        self.all_years.toggled.connect(lambda checked: self.year.setEnabled(not checked))
        inputs.addRow(self.all_years)
        self.query_button = QPushButton("Baixar polígonos da área pelo WFS (sem conta)")
        self.query_button.clicked.connect(self.download)
        local = QPushButton("Usar camada PRODES local / offline")
        local.clicked.connect(self.use_local)
        self.local_box = QComboBox()
        inputs.addRow(self.query_button)
        inputs.addRow("Camada local:", self.local_box)
        inputs.addRow(local)
        self.autofetch = QCheckBox("Buscar imagens, analisar e gerar relatório automaticamente")
        self.autofetch.setChecked(True)
        self.autofetch.setToolTip("Busca Landsat sem conta: ano PRODES e dois anteriores; reutiliza o acervo. Novas imagens exigem internet.")
        inputs.addRow(self.autofetch)
        self.clip_button = QPushButton("Recortar no imóvel e executar análise")
        self.clip_button.clicked.connect(self.prepare_and_fetch)
        inputs.addRow(self.clip_button)
        self.source_info = QLabel("Nenhuma base PRODES selecionada.")
        self.source_info.setWordWrap(True)
        inputs.addRow(self.source_info)
        source_scroll = QScrollArea()
        source_scroll.setWidgetResizable(True)
        source_scroll.setWidget(source_tab)
        self.tabs.addTab(source_scroll, "1 · Imóvel e PRODES")
        evidence_tab = QWidget()
        evidence_layout = QVBoxLayout(evidence_tab)
        guidance = QLabel("A análise automática busca o histórico anterior e posterior sem selecionar imagens manualmente.\n"
            "Para rasters RGB PRODES do catálogo: R=1, G=2, B=3. Para outros multibandas, indique os índices corretos.\n"
            "Cada conjunto deve cobrir o ano PRODES e os dois anteriores. Datas e bandas entram no relatório.")
        guidance.setWordWrap(True)
        evidence_layout.addWidget(guidance)
        self.images, self.dates, self.bands = [], [], []
        for index, label in enumerate(("Ano analisado", "Ano anterior", "Dois anos anteriores")):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            combo = QComboBox()
            row.addWidget(combo, 1)
            when = QDateEdit()
            when.setCalendarPopup(True)
            when.setDisplayFormat("dd/MM/yyyy")
            when.setDate(QDate(self.year.value() - index, 7, 1))
            row.addWidget(when)
            band_controls = []
            for channel, band in zip("RGB", (1, 2, 3)):
                row.addWidget(QLabel(channel))
                spin = QSpinBox()
                spin.setRange(1, 999)
                spin.setValue(band)
                row.addWidget(spin)
                band_controls.append(spin)
                spin.valueChanged.connect(self.invalidate)
            self.images.append(combo)
            self.dates.append(when)
            self.bands.append(band_controls)
            combo.currentIndexChanged.connect(lambda _, position=index: self.image_changed(position))
            when.dateChanged.connect(self.invalidate)
            evidence_layout.addLayout(row)
        historical_row = QHBoxLayout()
        historical_row.addWidget(QLabel("Referência anterior a 22/07/2008 (opcional):"))
        self.historical_box = QComboBox()
        historical_row.addWidget(self.historical_box, 1)
        self.historical_date = QLabel("Aquisição registrada no catálogo")
        historical_row.addWidget(self.historical_date)
        self.historical_box.currentIndexChanged.connect(self.historical_changed)
        evidence_layout.addLayout(historical_row)
        evidence_layout.addWidget(QLabel("A referência histórica usa SWIR1/NIR/vermelho e examina apenas a sobreposição com a consolidada.\n"
            "Pouca cobertura verde é uma pista; não comprova uso antrópico ou consolidação jurídica."))
        self.table = QTableWidget(0, 12)
        self.table.setHorizontalHeaderLabels(["UUID", "Interseção (ha)", "Além da borda (ha)",
            "Visual atual", "Visual anterior", "Visual dois anos antes", "Conferência visual", "Notas", "Triagem / resultado", "Minha revisão automática", "Consolidada sobreposta (ha)", "Indicador pré-marco"])
        evidence_layout.addWidget(self.table, 1)
        instructions = QLabel("Clique em Buscar histórico para pesquisar imagens antigas e posteriores por polígono.\n"
            "Depois, use Minha revisão automática e Notas para concordar/discordar. O parecer calculado será preservado.\n"
            "O modo assistido continua disponível, usando os três campos visuais e a conferência.")
        instructions.setWordWrap(True)
        evidence_layout.addWidget(instructions)
        actions = QHBoxLayout()
        self.automatic_button = QPushButton("Buscar histórico e analisar antes/depois automaticamente")
        self.automatic_button.clicked.connect(self.analyse_automatic)
        manual = QPushButton("Comparar somente as 3 imagens escolhidas (avançado)")
        manual.clicked.connect(self.analyse_selected_images)
        preview = QPushButton("Comparar imagens e limites")
        preview.clicked.connect(self.preview)
        compute = QPushButton("Avaliar evidências declaradas")
        compute.clicked.connect(self.analyse)
        add_layers = QPushButton("Adicionar recortes como camadas temporárias")
        add_layers.clicked.connect(self.add_layers)
        actions.addWidget(preview)
        actions.addWidget(self.automatic_button)
        evidence_layout.addWidget(manual)
        actions.addWidget(compute)
        actions.addWidget(add_layers)
        evidence_layout.addLayout(actions)
        self.tabs.addTab(evidence_tab, "2 · Evidências e avaliação")
        maps_tab = QWidget()
        maps_layout = QVBoxLayout(maps_tab)
        self.map_choice = QComboBox()
        self.map_choice.addItems(["Ano analisado", "Ano anterior", "Dois anos anteriores", "Referência anterior ao marco"])
        self.map_choice.currentIndexChanged.connect(self.update_map)
        maps_layout.addWidget(self.map_choice)
        self.canvas = QgsMapCanvas(self)
        self.canvas.setCanvasColor(QColor("#f2f5f5"))
        self.canvas.enableAntiAliasing(True)
        self.pan = QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(self.pan)
        maps_layout.addWidget(self.canvas, 1)
        maps_layout.addWidget(QLabel("Azul: imóvel · laranja: PRODES completo · vermelho: recortes · roxo: consolidada técnica."))
        self.tabs.addTab(maps_tab, "3 · Comparação no mapa")
        report_tab = QWidget()
        report_layout = QVBoxLayout(report_tab)
        self.report = QTextBrowser()
        self.report.setOpenExternalLinks(True)
        report_layout.addWidget(self.report)
        self.export_button = QPushButton("Exportar relatório PDF, mapas PNG, GeoPackage e manifesto")
        self.export_button.clicked.connect(self.export)
        self.export_button.setEnabled(False)
        report_layout.addWidget(self.export_button)
        self.last_export=""
        self.open_package_button=QPushButton("Abrir pasta do último pacote exportado")
        self.open_package_button.setEnabled(False)
        self.open_package_button.clicked.connect(self.open_package)
        report_layout.addWidget(self.open_package_button)
        self.tabs.addTab(report_tab, "4 · Relatório")
        footer = QHBoxLayout()
        self.info = QLabel("Pronto. Selecione o imóvel e inicie a investigação. Catálogo e bandas estão disponíveis em ferramentas avançadas.")
        self.info.setWordWrap(True)
        footer.addWidget(self.info, 1)
        self.cancel_button = QPushButton("Cancelar operação")
        self.cancel_button.clicked.connect(self.cancel)
        self.cancel_button.setEnabled(False)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)
        self.property_box.currentIndexChanged.connect(self.reset_analysis)
        self.consolidated_box.currentIndexChanged.connect(self.consolidated_changed)
        self.consolidated_origin.textChanged.connect(self.invalidate)
        self.consolidated_technical.toggled.connect(self.invalidate)
        for widget in (self.local_box, self.service_layers):
            widget.currentIndexChanged.connect(self.source_selection_changed)
        self.year.valueChanged.connect(self.reset_analysis)
        self.all_years.toggled.connect(self.reset_analysis)
        self.selected.toggled.connect(self.reset_analysis)
        self.car_boundary.toggled.connect(self.reset_analysis)
        self.annual.toggled.connect(self.invalidate)
        for widget in (self.name, self.car, self.reviewer):
            widget.textChanged.connect(self.review_changed)
        self.refresh_layers()

    def error(self, message):
        QMessageBox.warning(self, "Análise PRODES", str(message))

    def invalidate(self, *_):
        self.map_evidence = []
        self.generated_maps = []
        if hasattr(self, "map_choice"):
            self.map_choice.blockSignals(True)
            self.map_choice.clear()
            self.map_choice.addItems(["Ano PRODES", "Ano anterior", "Dois anos anteriores", "Referência pré-marco"])
            self.map_choice.blockSignals(False)
        self.automatic_results = None
        self.analysis_payload = None
        if hasattr(self, "canvas"):
            self.canvas.setLayers([])
        self.map_rasters = []
        self.export_button.setEnabled(False)
        self.report.clear()
        for item in self.rows:
            for key in ("status", "reason", "reviewed", "observations", "dates", "notes", "mode", "automatic", "spectral_signal", "thresholds", "user_review", "historical", "contestability", "consolidation_assessment", "history", "acquisition", "argumentation", "agent"):
                item.pop(key, None)
        if hasattr(self, "table"):
            for index in range(self.table.rowCount()):
                self.table.setItem(index, 8, QTableWidgetItem("Reavaliar"))
                self.table.setItem(index, 11, QTableWidgetItem("Reavaliar"))

    def reset_analysis(self, *_):
        self.invalidate()
        self.rows = []
        self.analysis_geometries = []
        self.consolidated_geometries = []
        self.consolidated_preview = None
        self.table.setRowCount(0)
        self.clipped = self.original = self.parcel = None
        self.canvas.setLayers([])
        self.map_rasters = []

    def source_selection_changed(self, *_):
        self.source = None
        self.source_note = ""
        self.source_info.setText("Fonte alterada: baixe novamente ou clique em Usar camada local antes de recortar.")
        self.reset_analysis()

    def consolidated_changed(self, *_):
        layer = QgsProject.instance().mapLayer(self.consolidated_box.currentData())
        recognised = False
        if layer:
            field = next((name for name in layer.fields().names() if name.lower() in ("id_tema", "tema")), None)
            if field:
                values = {str(feature[field]).strip().lower() for feature in layer.getFeatures(QgsFeatureRequest().setLimit(10000))}
                recognised = bool(values) and values <= {"consolidada", "area_consolidada", "área consolidada"}
        self.consolidated_technical.setChecked(recognised)
        self.reset_analysis()

    def historical_changed(self, *_):
        self.invalidate()
        layer = QgsProject.instance().mapLayer(self.historical_box.currentData())
        text = str(layer.customProperty("catalogo_multiespectral_data", "")) if layer else ""
        self.historical_date.setText(text or "Aquisição não informada")

    def update_cloud_constraint(self, value):
        if value==0:self.scene_cloud_strict.setChecked(False)
        elif value==20:self.scene_cloud_strict.setChecked(True)
        self.scene_cloud_strict.setEnabled(0<value<20)

    def refresh_layers(self):
        project = QgsProject.instance()
        boxes = [self.property_box, self.local_box, self.consolidated_box] + self.images + [self.historical_box]
        selected = [box.currentData() for box in boxes]
        for box in boxes:
            box.blockSignals(True)
            box.clear()
            box.addItem("Selecione…", None)
        for layer in project.mapLayers().values():
            if not layer.isValid():
                continue
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry:
                self.property_box.addItem(layer.name(), layer.id())
                self.local_box.addItem(layer.name(), layer.id())
                self.consolidated_box.addItem(layer.name(), layer.id())
            elif isinstance(layer, QgsRasterLayer) and layer.bandCount() >= 3:
                for box in self.images:
                    box.addItem(layer.name(), layer.id())
                self.historical_box.addItem(layer.name(), layer.id())
        for box, value in zip(boxes, selected):
            index = box.findData(value)
            if index >= 0:
                box.setCurrentIndex(index)
            box.blockSignals(False)
        self.reset_analysis()

    def snapshot_property(self):
        layer = QgsProject.instance().mapLayer(self.property_box.currentData())
        if not layer or not layer.isValid() or not layer.crs().isValid():
            raise ProdesError("Selecione uma camada de limite com SRC válido.")
        features = list(layer.getSelectedFeatures() if self.selected.isChecked() else layer.getFeatures())
        if not features and self.selected.isChecked() and layer.featureCount() == 1:
            features = list(layer.getFeatures())
        if not features:
            raise ProdesError("Selecione a feição do imóvel no QGIS ou desmarque a opção de seleção.")
        if len(features) > 1:
            raise ProdesError("Selecione uma única feição de imóvel. Dissolva explicitamente partes do mesmo imóvel antes de analisar.")
        geometry, repaired = polygon_copy(features[0].geometry(), "Limite do imóvel: " + layer.name())
        transform = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        geometry.transform(transform)
        parcel = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", self.name.text().strip() or layer.name(), "memory")
        feature = QgsFeature()
        feature.setGeometry(geometry)
        if not parcel.dataProvider().addFeatures([feature])[0]:
            raise ProdesError("Não foi possível criar cópia do imóvel.")
        parcel.updateExtents()
        outline(parcel, "0,135,225,255", 0.8)
        return parcel, geometry, repaired

    def snapshot_consolidated(self, property_geometry):
        layer_id = self.consolidated_box.currentData()
        if not layer_id:
            return None, None
        layer = QgsProject.instance().mapLayer(layer_id)
        if not layer or not layer.isValid() or not layer.crs().isValid():
            raise ProdesError("Área consolidada sem camada/SRC válido.")
        if layer.id() == self.property_box.currentData() or (self.source and layer.id() == self.source.id()):
            raise ProdesError("Escolha a consolidada separada do limite e dos incrementos PRODES.")
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        forward = QgsCoordinateTransform(layer.crs(), wgs, QgsProject.instance())
        backward = QgsCoordinateTransform(wgs, layer.crs(), QgsProject.instance())
        request = QgsFeatureRequest().setFilterRect(backward.transformBoundingBox(property_geometry.boundingBox()))
        parts, repairs, candidates = [], 0, 0
        for feature in layer.getFeatures(request):
            candidates += 1
            if candidates > 10000:
                raise ProdesError("Consolidada excede 10 mil feições na área. Recorte a fonte antes de analisar.")
            geometry, fixed = polygon_copy(feature.geometry(), "Consolidada: " + str(feature.id()))
            geometry.transform(forward)
            part = geometry.intersection(property_geometry)
            if part.isNull():
                raise ProdesError("Falha na interseção consolidada/imóvel: " + part.lastError())
            if not part.isEmpty() and part.area() > 0:
                part, intersection_fixed = polygon_copy(part, "Consolidada no imóvel")
                parts.append(part)
                repairs += int(fixed or intersection_fixed)
        self.consolidated_source_details = {"Fonte consolidada": layer.name() + " | " + layer.source(),
            "Atributos da consolidada": ", ".join(layer.fields().names()),
            "Feições consolidadas no imóvel": len(parts), "Correções da consolidada": repairs}
        if not parts:
            return None, None
        geometry, _ = polygon_copy(QgsGeometry.unaryUnion(parts), "União da consolidada")
        preview = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "Área rural consolidada — classificação técnica informada", "memory")
        feature = QgsFeature(); feature.setGeometry(geometry)
        if not preview.dataProvider().addFeatures([feature])[0]:
            raise ProdesError("Falha ao criar cópia da consolidada.")
        preview.updateExtents()
        outline(preview, "155,60,190,255", 0.5)
        return geometry, preview

    def run_query(self, action, callback, **kwargs):
        if self.job is not None:
            return
        self.job = QueryJob(action, parent=self, **kwargs)
        self.job.result.connect(callback)
        self.job.failed.connect(self.error)
        self.job.status.connect(self.info.setText)
        self.job.finished.connect(self.query_finished)
        # Freeze input while the worker uses its snapshot.
        self.tabs.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.info.setText("Consultando TerraBrasilis…")
        self.job.start()

    def query_finished(self):
        callback, self.after_job = self.after_job, None
        stopping = self.job.stopping
        self.job.deleteLater()
        self.job = None
        self.tabs.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if callback is not None and not stopping:
            QTimer.singleShot(0, callback)

    def cancel(self):
        if self.maps_in_progress:self.map_stopping=True
        if self.job:
            self.after_job = None
            self.job.stopping = True
            self.info.setText("Cancelando; aguardando a resposta de rede encerrar…")

    def discover(self):
        self.run_query("layers", self.got_layers)

    def got_layers(self, layers):
        self.service_layers.clear()
        available = annual_layers(layers)
        for name, title in available:
            self.service_layers.addItem(title + " [" + name + "]", name)
        self.info.setText("{} bases de incrementos por bioma. Mapas acumulados, limites e referências foram retirados desta lista.".format(len(available)))
        if not available:
            self.error("Nenhuma camada anual por bioma reconhecida no WFS. Use o arquivo oficial local.")

    def download(self):
        try:
            name = self.service_layers.currentData()
            if not name:
                raise ProdesError("Consulte e selecione uma camada do TerraBrasilis.")
            parcel, geometry, repaired = self.snapshot_property()
            rect = geometry.boundingBox()
            self.query_name = name
            self.query_property_hash = hashlib.sha256(geometry.asWkt().encode()).hexdigest()
            self.run_query("features", self.got_features, name=name,
                rect=(rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()))
        except Exception as exc:
            self.error(exc)

    def got_features(self, data):
        path = os.path.join(self.work.name, "prodes_consulta.geojson")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        self.source = QgsVectorLayer(path, self.query_name, "ogr")
        if not self.source.isValid() and data.get("features"):
            self.error("O QGIS não conseguiu abrir as feições recebidas.")
            self.source = None
            return
        if not data.get("features"):
            self.source = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", self.query_name, "memory")
        self.source_note = ENDPOINT + " | " + self.query_name + " | " + datetime.now(timezone.utc).isoformat()
        self.source_property_hash = self.query_property_hash
        self.annual.setChecked(True)
        if not self.agent_offline.isChecked():
            cache={'geometry_sha256':self.query_property_hash,'layer':self.query_name,'source_note':self.source_note,
                   'annual_confirmed':True,'data':data}
            cache_path=self.prodes_cache_path(self.query_property_hash,self.query_name)
            os.makedirs(os.path.dirname(cache_path),exist_ok=True)
            with open(cache_path+'.part','w',encoding='utf8') as stream:json.dump(cache,stream,ensure_ascii=False)
            os.replace(cache_path+'.part',cache_path)
        self.source_info.setText("Base WFS recebida: {} feições. Clique em Recortar.".format(len(data["features"])))
        self.reset_analysis()

    def start_pipeline(self):
        if self.job is not None:
            return
        try:
            _, geometry, _ = self.snapshot_property()
            self.snapshot_consolidated(geometry)
            extent = geometry.boundingBox()
            name = self.service_layers.currentData() or "prodes-amazon-nb:yearly_deforestation_biome"
            self.query_property_hash = hashlib.sha256(geometry.asWkt().encode()).hexdigest()
            self.autofetch.setChecked(True)
            if self.agent_offline.isChecked():
                path=self.prodes_cache_path(self.query_property_hash,name)
                if not os.path.isfile(path):
                    raise ProdesError('Não há PRODES em cache para esse limite e base. Faça uma consulta online uma vez ou use uma camada PRODES local na etapa 1.')
                with open(path,encoding='utf8') as stream:cache=json.load(stream)
                if cache.get('geometry_sha256')!=self.query_property_hash or cache.get('layer')!=name or not cache.get('annual_confirmed'):
                    raise ProdesError('Cache PRODES não corresponde ao limite/base preparados.')
                self.query_name=name;self.got_features(cache['data'])
                self.source_note=cache['source_note']+' | Cache offline, sem nova consulta ao INPE'
                self.source_info.setText('Base PRODES reutilizada do cache local; confira sua data de consulta.')
                QTimer.singleShot(0,self.prepare_and_fetch);return
            self.run_query("auto_features", self.got_pipeline_source, name=name,
                rect=(extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()))
        except Exception as exc:
            self.error(exc)

    def got_pipeline_source(self, value):
        self.query_name = value["name"]
        self.got_features(value["data"])
        if self.source is not None:
            self.after_job = self.prepare_and_fetch

    def use_local(self):
        source = QgsProject.instance().mapLayer(self.local_box.currentData())
        if not source:
            self.error("Selecione uma camada local PRODES.")
            return
        self.source = source
        self.source_property_hash = None
        self.source_note = "Camada local: " + source.name() + " | " + source.source()
        self.source_info.setText("Fonte local selecionada: " + source.name())
        self.reset_analysis()

    def prepare(self):
        self.reset_analysis()
        try:
            if not self.source or not self.source.isValid() or not self.source.crs().isValid():
                raise ProdesError("Baixe os polígonos ou selecione uma camada local com SRC válido.")
            parcel, property_geometry, repaired = self.snapshot_property()
            if getattr(self, "source_property_hash", None) and self.source_property_hash != hashlib.sha256(property_geometry.asWkt().encode()).hexdigest():
                raise ProdesError("O limite/seleção mudou desde a consulta. Baixe os polígonos novamente para esta área.")
            measure = QgsDistanceArea()
            measure.setSourceCrs(parcel.crs(), QgsProject.instance().transformContext())
            measure.setEllipsoid("GRS80")
            consolidated, consolidated_preview = self.snapshot_consolidated(property_geometry)
            core = None
            if self.car_boundary.isChecked():
                center = property_geometry.centroid().asPoint()
                zone = max(1, min(60, int((center.x() + 180) / 6) + 1))
                metric = QgsCoordinateReferenceSystem("EPSG:" + str((32700 if center.y() < 0 else 32600) + zone))
                forward = QgsCoordinateTransform(parcel.crs(), metric, QgsProject.instance())
                backward = QgsCoordinateTransform(metric, parcel.crs(), QgsProject.instance())
                core = QgsGeometry(property_geometry)
                core.transform(forward)
                core = core.buffer(-60, 16)
                if core.isEmpty():
                    raise ProdesError("O imóvel não tem núcleo após recuo de 60 m. Desative a tolerância e faça revisão manual.")
                core.transform(backward)
            clipped = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "PRODES — recorte do imóvel", "memory")
            original = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "PRODES — polígonos completos", "memory")
            for layer in (clipped, original):
                layer.dataProvider().addAttributes(self.source.fields())
                layer.updateFields()
            to_wgs = QgsCoordinateTransform(self.source.crs(), parcel.crs(), QgsProject.instance())
            fields = self.source.fields().names()
            class_field = next((field for field in fields if field.lower() in ("class_name", "classname")), None)
            if class_field is None and self.source.featureCount() > 0:
                raise ProdesError("A camada não contém class_name/classname. Selecione a base oficial de incrementos por bioma.")
            to_source = QgsCoordinateTransform(parcel.crs(), self.source.crs(), QgsProject.instance())
            request = QgsFeatureRequest().setFilterRect(to_source.transformBoundingBox(property_geometry.boundingBox()))
            rows, clip_features, original_features = [], [], []
            consolidated_geometries = []
            repaired_count = 0
            available_years = {}
            candidates = 0
            unrecognised = set()
            for feature in self.source.getFeatures(request):
                candidates += 1
                properties = dict(zip(self.source.fields().names(), feature.attributes()))
                item = record(properties)
                if item["year"] is None:
                    unrecognised.add(item["class"])
                    continue
                feature_context = "PRODES {} | UUID {} | feição {}".format(item["class"], item["uuid"], feature.id())
                geometry, fixed = polygon_copy(feature.geometry(), feature_context)
                geometry.transform(to_wgs)
                if not geometry.boundingBox().intersects(property_geometry.boundingBox()) or not geometry.intersects(property_geometry):
                    continue
                part = geometry.intersection(property_geometry)
                if part.isNull():
                    raise ProdesError("Falha na interseção: " + part.lastError())
                if part.isEmpty() or part.area() == 0:
                    continue
                part, intersection_fixed = polygon_copy(part, "Recorte " + feature_context)
                available_years[item["year"]] = available_years.get(item["year"], 0) + 1
                if not self.all_years.isChecked() and item["year"] != self.year.value():
                    continue
                core_ha = None
                if core is not None:
                    inside = part.intersection(core)
                    if inside.isNull():
                        raise ProdesError("Falha na interseção com a zona de tolerância.")
                    core_ha = measure.measureArea(inside) / 10000 if not inside.isEmpty() else 0.0
                item.update(geometry_repaired=bool(fixed or intersection_fixed), original_ha=measure.measureArea(geometry) / 10000,
                    clip_ha=measure.measureArea(part) / 10000, core_ha=core_ha)
                overlap = part.intersection(consolidated) if consolidated is not None else QgsGeometry()
                if consolidated is not None and overlap.isNull():
                    raise ProdesError("Falha na interseção consolidada/PRODES: " + item["uuid"])
                if not overlap.isEmpty() and overlap.area() > 0:
                    overlap, _ = polygon_copy(overlap, "Consolidada/PRODES " + item["uuid"])
                    item["consolidated_ha"] = measure.measureArea(overlap) / 10000
                    consolidated_geometries.append(overlap.asWkt())
                else:
                    item["consolidated_ha"] = 0.0
                    consolidated_geometries.append("")
                rows.append(item)
                for target, geom in ((clip_features, part), (original_features, geometry)):
                    new = QgsFeature(clipped.fields())
                    new.setGeometry(geom)
                    new.setAttributes(feature.attributes())
                    target.append(new)
                repaired_count += int(fixed or intersection_fixed)
            for layer, features in ((clipped, clip_features), (original, original_features)):
                if features and not layer.dataProvider().addFeatures(features)[0]:
                    raise ProdesError("Falha ao criar o recorte vetorial.")
                layer.updateExtents()
            outline(clipped, "225,42,45,255", 0.7)
            outline(original, "235,151,41,255", 0.4)
            self.reset_analysis()
            self.parcel, self.clipped, self.original, self.rows = parcel, clipped, original, rows
            self.analysis_geometries = [feature.geometry().asWkt() for feature in clip_features]
            self.consolidated_geometries = consolidated_geometries
            self.consolidated_preview = consolidated_preview
            self.prepared_consolidated_hash = hashlib.sha256((consolidated.asWkt() if consolidated is not None else "").encode()).hexdigest()
            self.prepared_details = {"Fonte do limite": parcel.name(), "Geometria do imóvel corrigida": repaired,
                "Feições PRODES corrigidas": repaired_count, "Tolerância CAR": "60 m" if core is not None else "desativada",
                "Anos presentes no imóvel": ", ".join(str(value) for value in sorted(available_years)) or "Nenhum",
                "Feições recebidas na fonte": self.source.featureCount(), "Candidatas no envelope": candidates,
                "Fonte utilizada": self.source_note,
                "Envelope do imóvel (longitude/latitude)": property_geometry.boundingBox().toString()}
            if self.consolidated_box.currentData():
                self.prepared_details.update(self.consolidated_source_details)
            self.populate()
            years_text = ", ".join("{} ({} polígonos)".format(year, count) for year, count in sorted(available_years.items())) or "nenhum"
            self.info.setText("{} polígonos exibidos. Anos que interceptam o imóvel: {}.".format(len(rows), years_text))
            self.update_map()
            self.tabs.setCurrentIndex(1)
            if not rows:
                details = "Nenhum polígono exibido neste filtro.\nFonte: {}\nFeições na fonte: {}; candidatas na área: {}\nAnos que interceptam o imóvel: {}\nClasses não reconhecidas: {}\nEnvelope longitude/latitude: {}".format(
                    self.source_note, self.source.featureCount(), candidates, years_text,
                    ", ".join(sorted(unrecognised))[:500] or "nenhuma", property_geometry.boundingBox().toString())
                details += "\nResultado vazio não comprova ausência de desmatamento. O histórico anterior ao início da base anual pode estar em produtos acumulados, que não são avaliados neste módulo."
                QMessageBox.information(self, "Diagnóstico da consulta PRODES", details)
        except Exception as exc:
            self.error(exc)

    def prepare_and_fetch(self):
        if self.job is not None:
            return
        self.prepare()
        if self.rows and self.autofetch.isChecked():
            self.analyse_autofetch()

    def archive_root(self):
        return QgsSettings().value('catalogo_multiespectral/acervo','',type=str) or os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation),'Catalogo_Multiespectral_Acervo')

    def prodes_cache_path(self,signature,layer):
        identity=hashlib.sha256((signature+'|'+layer).encode()).hexdigest()
        return os.path.join(self.archive_root(),'prodes_cache',identity+'.geojson')

    def input_rows(self):
        computed={'status','reason','reviewed','observations','dates','notes','mode','automatic','spectral_signal','thresholds','user_review','historical','contestability','consolidation_assessment','history','acquisition','argumentation','agent'}
        return [{key:value for key,value in json.loads(json.dumps(row)).items() if key not in computed} for row in self.rows]

    def acquisition_payload(self):
        if not self.rows or not self.parcel:
            raise ProdesError("Prepare os recortes PRODES antes de analisar.")
        _, current, _ = self.snapshot_property()
        prepared = next(self.parcel.getFeatures()).geometry()
        if current.asWkt() != prepared.asWkt():
            raise ProdesError("O limite mudou. Prepare os recortes novamente.")
        consolidated, _ = self.snapshot_consolidated(current)
        signature = hashlib.sha256((consolidated.asWkt() if consolidated is not None else "").encode()).hexdigest()
        if signature != self.prepared_consolidated_hash:
            raise ProdesError("A geometria consolidada mudou. Prepare os recortes novamente.")
        extent = current.boundingBox()
        root = QgsSettings().value("catalogo_multiespectral/acervo", "", type=str)
        if not root:
            root = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation), "Catalogo_Multiespectral_Acervo")
        return {"rows": self.input_rows(), "geometries": list(self.analysis_geometries),
            "consolidated_geometries": list(self.consolidated_geometries), "parcel_geometry": current.asWkt(),
            "rect": [extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum()],
            "target_crs": (QgsProject.instance().mapLayer(self.property_box.currentData()).crs().authid()
                or QgsProject.instance().mapLayer(self.property_box.currentData()).crs().toWkt()),
            "agent_cloud_max": self.scene_cloud_limit.value(), "agent_cloud_strict": self.scene_cloud_strict.isChecked(),
            "archive_root": root, "annual": self.annual.isChecked(), "tolerance": self.car_boundary.isChecked(),
            "history_enabled": True, "history_start_year": self.history_start.value(),
            "agent_enabled":self.agent_enabled.isChecked(), "agent_profile":self.agent_profile.currentData(), "agent_offline":self.agent_offline.isChecked(),
            "amazon_forest": "prodes-amazon-nb:" in self.source_note,
            "consolidated_technical": bool(self.consolidated_box.currentData() and self.consolidated_technical.isChecked()),
            "consolidated_origin": self.consolidated_origin.text().strip()}

    def analyse_autofetch(self):
        if self.job is not None:
            return
        try:
            if self.vision_enabled.isChecked() and not self.vision_model.currentText().strip():
                raise ProdesError("Informe um modelo multimodal local ou desmarque a interpretação visual. A investigação espectral funciona sem modelo.")
            payload = self.acquisition_payload()
            if not payload["annual"]:
                raise ProdesError("Confirme a fonte de incremento anual por bioma antes da busca automática.")
            self.invalidate()
            self.job = AutoEvidenceJob(payload, self)
            self.job.result.connect(self.finish_autofetch)
            self.job.failed.connect(self.error)
            self.job.status.connect(self.info.setText)
            self.job.finished.connect(self.query_finished)
            self.tabs.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.info.setText("Buscando imagens e preparando evidências automaticamente…")
            self.job.start()
        except Exception as exc:
            self.error(exc)

    def finish_autofetch(self, value):
        from .plugin import CatalogDialog
        try:
            self.analysis_payload = value["payload"]
            self.map_evidence = self.analysis_payload["images"]
            self.map_rasters = []
            self.map_choice.blockSignals(True)
            self.map_choice.clear()
            for image in self.map_evidence:
                layer = QgsRasterLayer(image["path"], image["date"] + " · " + image["name"], "gdal")
                if not layer.isValid():
                    raise ProdesError("Raster automático inválido: " + image["name"])
                layer.setCustomProperty("catalogo_multiespectral_data", image["date"])
                layer.setCustomProperty("catalogo_multiespectral_cena", image["scene_id"])
                layer.setCustomProperty("catalogo_multiespectral_bandas", "swir16,nir08,red")
                layer.setCustomProperty("catalogo_multiespectral_espectral", json.dumps(image["metadata"]))
                CatalogDialog.configure_rgb(layer, smooth=False)
                if self.analysis_payload.get("agent_enabled"):
                    self.configure_comparable_rgb(layer,image)
                self.map_rasters.append(layer)
                self.map_choice.addItem(image["date"] + " · " + image["scene_id"])
                if not any(isinstance(existing, QgsRasterLayer) and existing.source() == layer.source()
                           for existing in QgsProject.instance().mapLayers().values()):
                    QgsProject.instance().addMapLayer(layer.clone())
            self.map_choice.blockSignals(False)
            self.finish_automatic(value["results"])
            for image in self.analysis_payload.get("available_images", []):
                if any(isinstance(existing, QgsRasterLayer) and existing.source() == image["path"]
                       for existing in QgsProject.instance().mapLayers().values()):
                    continue
                layer = QgsRasterLayer(image["path"], image["date"] + " · " + image["name"], "gdal")
                if not layer.isValid():
                    continue
                layer.setCustomProperty("catalogo_multiespectral_data", image["date"])
                layer.setCustomProperty("catalogo_multiespectral_cena", image["scene_id"])
                layer.setCustomProperty("catalogo_multiespectral_bandas", "swir16,nir08,red")
                layer.setCustomProperty("catalogo_multiespectral_espectral", json.dumps(image["metadata"]))
                CatalogDialog.configure_rgb(layer)
                QgsProject.instance().addMapLayer(layer)
                node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
                if node:
                    node.setItemVisibilityChecked(False)
            self.generated_maps=[]
            self.render_report()
            self.update_map()
            self.after_job=self.start_map_generation
        except Exception as exc:
            self.map_choice.blockSignals(False)
            self.error(exc)

    def start_map_generation(self):
        self.pending_maps=iter(self.report_map_tasks())
        self.maps_in_progress=True;self.map_stopping=False
        self.tabs.setEnabled(False);self.export_button.setEnabled(False);self.cancel_button.setEnabled(True)
        QTimer.singleShot(0,self.next_map)

    def next_map(self):
        if self.map_stopping:
            self.maps_in_progress=False;self.tabs.setEnabled(True);self.cancel_button.setEnabled(False)
            self.info.setText('Produção de mapas cancelada. Execute a investigação novamente para concluir o pacote.');return
        try:
            task=next(self.pending_maps,None)
            if task is None:
                self.maps_in_progress=False;self.tabs.setEnabled(True);self.cancel_button.setEnabled(False);self.export_button.setEnabled(True)
                self.render_report()
                if self.vision_enabled.isChecked():self.start_visual()
                else:self.complete_investigation()
                return
            polygon_index,index,raster=task
            self.info.setText('Produzindo carta {} · polígono {}…'.format(len(self.generated_maps)+1,polygon_index+1))
            self.generated_maps.append(self.report_map_value(polygon_index,index,raster,self.work.name))
            QTimer.singleShot(0,self.next_map)
        except Exception as exc:
            self.maps_in_progress=False;self.tabs.setEnabled(True);self.cancel_button.setEnabled(False)
            self.error('Não foi possível concluir mapas/relatório: '+str(exc))

    def configure_comparable_rgb(self,layer,image):
        provider=layer.dataProvider();renderer=QgsMultiBandColorRenderer(provider,1,2,3)
        coefficients=image['metadata'].get('coefficients',[])
        if len(coefficients)<3:return
        for band,setter in [(1,renderer.setRedContrastEnhancement),(2,renderer.setGreenContrastEnhancement),(3,renderer.setBlueContrastEnhancement)]:
            scale,offset=coefficients[band-1]
            enhancement=QgsContrastEnhancement(provider.dataType(band))
            enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
            enhancement.setMinimumValue((.02-offset)/scale);enhancement.setMaximumValue((.45-offset)/scale)
            setter(enhancement)
        layer.setRenderer(renderer)
        layer.setCustomProperty('investigacao_contraste','Reflectância 0.02–0.45; mesmos limites físicos em todas as datas; sem suavização')

    def discover_models(self):
        if self.job is not None:return
        self.job=VisionJob({'list_models':True},self)
        self.job.result.connect(self.got_models);self.job.failed.connect(self.error)
        self.job.finished.connect(self.query_finished)
        self.tabs.setEnabled(False);self.cancel_button.setEnabled(True)
        self.info.setText('Consultando modelos locais; nenhuma carta foi enviada…');self.job.start()

    def got_models(self,names):
        self.vision_model.clear();self.vision_model.addItems(names)
        self.info.setText('{} modelos locais encontrados; a capacidade de visão será verificada antes da interpretação.'.format(len(names)))

    def start_visual(self):
        if self.job is not None:return
        cards=[]
        for value in self.generated_maps:
            row=self.rows[value['polygon_index']]
            from .prodes_agent import visual_scene_order
            usable_ids=set(visual_scene_order(row))
            if value.get('scene_id') not in usable_ids:continue
            path=os.path.join(self.work.name,'ia_{}_{}.png'.format(value['polygon_index'],len(cards)))
            image=QImage(value['filename'])
            if image.isNull():continue
            image.scaledToWidth(1600).save(path,'PNG')
            cards.append(dict(value,filename=path))
        self.job=VisionJob({'model':self.vision_model.currentText().strip(),'rows':json.loads(json.dumps(self.rows)), 'cards':cards},self)
        self.job.result.connect(self.finish_visual);self.job.failed.connect(self.error)
        self.job.status.connect(self.info.setText);self.job.finished.connect(self.query_finished)
        self.tabs.setEnabled(False);self.export_button.setEnabled(False);self.cancel_button.setEnabled(True)
        self.info.setText('Interpretando cartas-imagem na IA local…');self.job.start()

    def finish_visual(self,values):
        for row,value in zip(self.rows,values):
            row.setdefault('agent',{})['visual']=value
            row['agent']['visual_status']=value['status']
        self.render_report();self.export_button.setEnabled(True)
        self.after_job=self.complete_investigation

    def complete_investigation(self):
        try:self._complete_investigation()
        except Exception as exc:self.error("Não foi possível concluir o pacote: "+str(exc))

    def _complete_investigation(self):
        if not self.analysis_payload:return
        receipt=self.analysis_payload.get('investigation')
        if receipt:
            append_event(receipt,'cartas_e_interpretacao',{'map_count':len(self.generated_maps),
                'maps':[{'scene_id':v.get('scene_id'),'polygon_index':v['polygon_index'],
                         'sha256':hashlib.sha256(open(v['filename'],'rb').read()).hexdigest()} for v in self.generated_maps],
                'visual':[r.get('agent',{}).get('visual',{'status':'Não solicitada'}) for r in self.rows]})
            from .prodes_agent import AGENT_VERSION
            self.context['Sistema de investigação']=AGENT_VERSION
            self.context['Identificador da investigação']=receipt['run_id']
            self.context['Contraste das cartas']='Mesmos limites de reflectância 0.02–0.45; pixels sem suavização'
            state=dict(receipt,status='cartas_e_relatorio_prontos',visual_requested=self.vision_enabled.isChecked())
            state.pop('directory',None)
            path=os.path.join(receipt['directory'],'session.json')
            with open(path+'.part','w',encoding='utf8') as stream:json.dump(state,stream,ensure_ascii=False,indent=2)
            os.replace(path+'.part',path)
            receipt.update(status=state['status'])
        self.render_report()
        if self.auto_export.isChecked():
            root=os.path.join(self.analysis_payload['archive_root'],'relatorios')
            os.makedirs(root,exist_ok=True);self.export(root)
        else:self.info.setText('Investigação concluída. Confira as hipóteses, revise e exporte o pacote.')

    def populate(self):
        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            for column, value in enumerate((row["class"] + " | " + (row["uuid"] or "UUID ausente"), "{:.4f}".format(row["clip_ha"]),
                    "{:.4f}".format(row["core_ha"]) if row["core_ha"] is not None else "—")):
                self.table.setItem(index, column, QTableWidgetItem(value))
            for column in (3, 4, 5):
                combo = QComboBox()
                for label, value in (("Não avaliado / insuficiente", "unknown"), ("Vegetação nativa", "native"), ("Supressão observável", "suppressed")):
                    combo.addItem(label, value)
                combo.currentIndexChanged.connect(self.invalidate)
                self.table.setCellWidget(index, column, combo)
            check = QCheckBox("Conferida")
            check.toggled.connect(self.invalidate)
            self.table.setCellWidget(index, 6, check)
            notes = QLineEdit()
            notes.textChanged.connect(self.review_changed)
            self.table.setCellWidget(index, 7, notes)
            self.table.setItem(index, 8, QTableWidgetItem("Inconclusivo"))
            self.table.setItem(index, 10, QTableWidgetItem("{:.4f}".format(row.get("consolidated_ha", 0))))
            self.table.setItem(index, 11, QTableWidgetItem("Não avaliado"))
            review = QComboBox()
            review.addItems(["A revisar", "Concordo", "Discordo"])
            review.currentIndexChanged.connect(self.review_changed)
            self.table.setCellWidget(index, 9, review)
        self.table.resizeColumnsToContents()

    def image_changed(self, index):
        self.invalidate()
        layer = QgsProject.instance().mapLayer(self.images[index].currentData())
        if layer:
            text = layer.customProperty("catalogo_multiespectral_data", "")
            date_value = QDate.fromString(str(text), "yyyy-MM-dd")
            if date_value.isValid():
                self.dates[index].setDate(date_value)
        self.map_rasters = []

    def build_rasters(self, required=False):
        result = []
        for index, box in enumerate(self.images):
            source = QgsProject.instance().mapLayer(box.currentData())
            if not source:
                if required:
                    raise ProdesError("Selecione as três imagens do conjunto temporal.")
                result.append(None)
                continue
            bands = [spin.value() for spin in self.bands[index]]
            if max(bands) > source.bandCount():
                raise ProdesError("Índice de banda excede o número de bandas da imagem: " + source.name())
            clone = QgsRasterLayer(source.source(), source.name(), source.providerType())
            if not clone.isValid():
                raise ProdesError("Não foi possível abrir a imagem: " + source.name())
            if source.renderer():
                clone.setRenderer(source.renderer().clone())
            renderer = clone.renderer()
            if isinstance(renderer, QgsMultiBandColorRenderer):
                renderer.setRedBand(bands[0])
                renderer.setGreenBand(bands[1])
                renderer.setBlueBand(bands[2])
            else:
                clone.setRenderer(QgsMultiBandColorRenderer(clone.dataProvider(), *bands))
            result.append(clone)
        historical = QgsProject.instance().mapLayer(self.historical_box.currentData())
        if historical:
            clone = QgsRasterLayer(historical.source(), historical.name(), historical.providerType())
            if not clone.isValid():
                raise ProdesError("Não foi possível abrir a referência histórica.")
            keys = str(historical.customProperty("catalogo_multiespectral_bandas", "")).split(",")
            wanted = ["B11", "B08", "B04"] if "B11" in keys else ["swir16", "nir08", "red"]
            if not all(key in keys for key in wanted):
                raise ProdesError("Referência histórica sem bandas PRODES identificadas.")
            if historical.renderer():
                clone.setRenderer(historical.renderer().clone())
            bands = [keys.index(key) + 1 for key in wanted]
            renderer = clone.renderer()
            if isinstance(renderer, QgsMultiBandColorRenderer):
                renderer.setRedBand(bands[0]); renderer.setGreenBand(bands[1]); renderer.setBlueBand(bands[2])
            else:
                clone.setRenderer(QgsMultiBandColorRenderer(clone.dataProvider(), *bands))
            result.append(clone)
        return result

    def preview(self):
        try:
            if not self.parcel:
                raise ProdesError("Prepare o recorte primeiro.")
            self.map_rasters = self.build_rasters(required=True)
            self.update_map()
            self.tabs.setCurrentIndex(2)
        except Exception as exc:
            self.error(exc)

    def add_layers(self):
        if not self.rows:
            self.error("Nenhum polígono preparado. Confira o diagnóstico da consulta antes de adicionar camadas.")
            return
        if not self.parcel or not self.clipped:
            self.error("Prepare o recorte primeiro.")
            return
        project = QgsProject.instance()
        for layer in (self.parcel, self.original, self.clipped, self.consolidated_preview):
            if layer is not None:
                project.addMapLayer(layer.clone())
        self.info.setText("Imóvel, polígonos completos e recortes adicionados ao projeto como camadas temporárias.")

    def update_map(self, *_):
        if not self.parcel:
            return
        position = self.map_choice.currentIndex()
        raster = self.map_rasters[position] if position < len(self.map_rasters) else None
        self.canvas.setDestinationCrs(self.parcel.crs())
        self.canvas.setLayers([layer for layer in (self.parcel, self.clipped, self.consolidated_preview, self.original, raster) if layer is not None])
        extent = self.parcel.extent()
        extent.scale(1.5)
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def automatic_payload(self):
        if not self.rows or not self.parcel:
            raise ProdesError("Prepare os recortes PRODES antes de analisar.")
        _, current, _ = self.snapshot_property()
        prepared = next(self.parcel.getFeatures()).geometry()
        if current.asWkt() != prepared.asWkt():
            raise ProdesError("O limite mudou. Prepare os recortes novamente.")
        consolidated, _ = self.snapshot_consolidated(current)
        signature = hashlib.sha256((consolidated.asWkt() if consolidated is not None else "").encode()).hexdigest()
        if signature != self.prepared_consolidated_hash:
            raise ProdesError("A geometria consolidada mudou. Prepare os recortes novamente.")
        dates = [widget.date().toString("yyyy-MM-dd") for widget in self.dates]
        images, scenes = [], []
        for index, box in enumerate(self.images):
            layer = QgsProject.instance().mapLayer(box.currentData())
            if not layer or not layer.isValid() or not os.path.isfile(layer.source()):
                raise ProdesError("Selecione três composições PRODES locais e georreferenciadas do catálogo.")
            acquired = str(layer.customProperty("catalogo_multiespectral_data", ""))
            if not acquired or acquired != dates[index]:
                raise ProdesError("Data de aquisição ausente ou diferente do formulário: " + layer.name())
            scene = str(layer.customProperty("catalogo_multiespectral_cena", ""))
            if not scene or scene in scenes:
                raise ProdesError("Escolha três cenas distintas com data e origem registradas pelo catálogo.")
            scenes.append(scene)
            keys = str(layer.customProperty("catalogo_multiespectral_bandas", "")).split(",")
            bands = [spin.value() for spin in self.bands[index]]
            if len(keys) != layer.bandCount() or len(set(bands)) != 3 or max(bands) > len(keys):
                raise ProdesError("Bandas RGB ou metadados inválidos: " + layer.name())
            mapped = [keys[band - 1] for band in bands]
            if mapped not in (["swir16", "nir08", "red"], ["B11", "B08", "B04"]):
                raise ProdesError("A análise requer SWIR1/NIR/vermelho (composição PRODES), nesta ordem. Importe esse preset para cada data.")
            metadata = metadata_for_layer(layer.source(), scene, keys,
                layer.customProperty("catalogo_multiespectral_espectral", ""))
            if len(metadata.get("coefficients", [])) != len(keys):
                raise ProdesError("Calibração incompleta para as bandas da cena.")
            images.append({"path": layer.source(), "name": layer.name(), "scene_id": scene,
                           "bands": bands, "metadata": metadata})
        historical_image = None
        layer = QgsProject.instance().mapLayer(self.historical_box.currentData())
        if layer:
            acquired = str(layer.customProperty("catalogo_multiespectral_data", ""))
            date_value = QDate.fromString(acquired, "yyyy-MM-dd")
            if not date_value.isValid() or date_value >= QDate(2008, 7, 22):
                raise ProdesError("Selecione referência com aquisição anterior a 22/07/2008 registrada no catálogo.")
            if not layer.isValid() or not os.path.isfile(layer.source()):
                raise ProdesError("A referência histórica precisa ser um raster local válido.")
            scene = str(layer.customProperty("catalogo_multiespectral_cena", ""))
            keys = str(layer.customProperty("catalogo_multiespectral_bandas", "")).split(",")
            wanted = ["B11", "B08", "B04"] if "B11" in keys else ["swir16", "nir08", "red"]
            if len(keys) != layer.bandCount() or not all(key in keys for key in wanted):
                raise ProdesError("Importe a referência pré-marco com as bandas PRODES SWIR1/NIR/vermelho.")
            metadata = metadata_for_layer(layer.source(), scene, keys,
                layer.customProperty("catalogo_multiespectral_espectral", ""))
            historical_image = {"path": layer.source(), "name": layer.name(), "date": acquired,
                "scene_id": scene, "bands": [keys.index(key) + 1 for key in wanted], "metadata": metadata}
        return {"rows": self.input_rows(), "geometries": list(self.analysis_geometries),
                "images": images, "dates": dates, "annual": self.annual.isChecked(),
                "tolerance": self.car_boundary.isChecked(), "historical_image": historical_image,
                "consolidated_geometries": list(self.consolidated_geometries),
                "consolidated_technical": bool(self.consolidated_box.currentData() and self.consolidated_technical.isChecked()),
                "consolidated_origin": self.consolidated_origin.text().strip()}

    def analyse_automatic(self):
        """Always acquire the historical series; selectors belong to manual mode."""
        if self.job is not None:
            return
        self.autofetch.setChecked(True)
        if self.rows and self.annual.isChecked():
            self.analyse_autofetch()
        else:
            self.start_pipeline()

    def analyse_selected_images(self):
        if self.job is not None:
            return
        try:
            payload = self.automatic_payload()
            self.invalidate()
            self.analysis_payload = payload
            self.map_rasters = self.build_rasters(required=True)
            self.job = AnalysisJob(payload, self)
            self.job.result.connect(self.finish_automatic)
            self.job.failed.connect(self.error)
            self.job.status.connect(self.info.setText)
            self.job.finished.connect(self.query_finished)
            self.tabs.setEnabled(False)
            self.cancel_button.setEnabled(True)
            self.info.setText("Calculando índices e verificando a cobertura local…")
            self.job.start()
        except Exception as exc:
            self.error(exc)

    def review_changed(self, *_):
        if self.automatic_results is not None:
            self.finish_automatic(self.automatic_results, refresh_review=True)
        else:
            self.invalidate()

    def finish_automatic(self, results, refresh_review=False):
        if len(results) != len(self.rows):
            self.error("Resultados não correspondem aos recortes preparados.")
            return
        self.automatic_results = results
        if not refresh_review:
            self.analysis_time = datetime.now(timezone.utc).isoformat()
        for index, (item, result) in enumerate(zip(self.rows, results)):
            item.update(result)
            review = self.table.cellWidget(index, 9)
            if not refresh_review:
                review.blockSignals(True)
                review.setCurrentIndex(0)
                review.blockSignals(False)
            item["user_review"] = review.currentText()
            item["reviewed"] = review.currentText() != "A revisar"
            item["notes"] = self.table.cellWidget(index, 7).text()
            self.table.setItem(index, 8, QTableWidgetItem(item.get("contestability", {}).get("status", item["status"])))
            self.table.setItem(index, 11, QTableWidgetItem(item.get("historical", {}).get("status", "Não avaliado")))
        self.context = {"Imóvel": self.name.text().strip() or self.parcel.name(),
            "CAR": self.car.text().strip() or "Não informado", "Revisor": self.reviewer.text().strip() or "Não informado",
            "Fonte PRODES": self.source_note, "Análise UTC": self.analysis_time,
            "Atualização da revisão UTC": datetime.now(timezone.utc).isoformat(),
            "Modo": "Triagem automática de contestação PRODES",
            "Fluxo de análise": "Busca histórica anterior/posterior" if self.analysis_payload.get("history_enabled") else "Comparação manual de três imagens; histórico não pesquisado", "Regras": CONTEST_RULE_VERSION, "Relatório simples": True,
            "Limiares experimentais próprios": THRESHOLDS, **self.prepared_details}
        for index, image in enumerate(self.analysis_payload["images"]):
            self.context["Imagem {}".format(index + 1)] = "{} | {} | RGB={} | {}".format(image["name"],
                self.analysis_payload["dates"][index], "/".join(map(str, image["bands"])), image["metadata"]["calibration_source"])
        self.context["Incremento por bioma confirmado"] = self.analysis_payload["annual"]
        self.context["Filtro de nuvens da cena"] = ('menos de ' if self.analysis_payload.get('agent_cloud_strict',True) else 'até ')+str(self.analysis_payload.get('agent_cloud_max',20))+'%; não certifica nuvens no recorte' 
        self.context["Consolidada conforme classificação técnica informada"] = self.analysis_payload["consolidated_technical"]
        self.context["Origem/evidências técnicas da consolidada"] = self.analysis_payload["consolidated_origin"] or "Não detalhadas"
        historic = self.analysis_payload.get("historical_image")
        self.context["Imagem anterior ao marco"] = (historic["name"] + " | " + historic["date"]) if historic else "Não fornecida; classificação técnica não verificada por imagem pré-marco neste processamento"
        if self.analysis_payload.get("acquisition_policy"):
            self.context["Busca automática de evidências"] = self.analysis_payload["acquisition_policy"]
            self.context["Avisos da aquisição"] = self.analysis_payload["acquisition_warnings"] or "Nenhum"
            self.context["Sequências por registro PRODES"] = [{"ano": group["year"], "referência": group["reference_date"],
                "origem da referência": group["reference_date_source"], "satélite preferido": group["preferred_platform"]}
                for group in self.analysis_payload["acquisition_groups"]]
        self.render_report()
        self.export_button.setEnabled(True)
        if not refresh_review:
            self.tabs.setCurrentIndex(3)
            self.info.setText("Relatório automático pronto. Na aba 2, marque Concordo/Discordo e registre notas; o relatório será atualizado.")

    @staticmethod
    def attach_map_resources(document, maps):
        from .prodes_report import normalized_maps, image_uri
        for value in normalized_maps(maps):
            image = QImage(value["filename"])
            if image.isNull():
                raise ProdesError("Mapa não pôde ser incorporado ao relatório: " + value["filename"])
            document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(image_uri(value["filename"])), image)
        document.markContentsDirty(0, document.characterCount())

    def render_report(self):
        self.report.setHtml(report_html(self.context, self.rows, self.generated_maps))
        self.attach_map_resources(self.report.document(), self.generated_maps)

    def report_map_tasks(self):
        result=[]
        for polygon_index,row in enumerate(self.rows):
            wanted=row.get('history',{}).get('map_scene_ids',[])
            for index,raster in enumerate(self.map_rasters):
                if raster is None:continue
                evidence=self.map_evidence[index] if self.map_evidence else {}
                if wanted and evidence.get('scene_id') not in wanted:continue
                if row.get('history') and not wanted:continue
                if not row.get('history') and self.map_date(index).year() not in (row.get('year'),row.get('year',0)-1,row.get('year',0)-2):continue
                result.append((polygon_index,index,raster))
        return result

    def report_map_value(self,polygon_index,index,raster,directory):
        evidence=self.map_evidence[index] if self.map_evidence else {}
        return {'caption':'Polígono {} · PRODES RGB · {}'.format(polygon_index+1,self.map_date(index).toString('dd/MM/yyyy')),
                'polygon_index':polygon_index,'scene_id':evidence.get('scene_id',''),'date':self.map_date(index).toString('yyyy-MM-dd'),
                'filename':os.path.join(directory,self.export_map(raster,index,directory,polygon_index))}

    def make_report_maps(self,directory):
        return [self.report_map_value(polygon_index,index,raster,directory) for polygon_index,index,raster in self.report_map_tasks()]

    def analyse(self):
        try:
            self.invalidate()
            if not self.rows:
                raise ProdesError("Nenhum polígono preparado. Confira a fonte, os anos e o diagnóstico da consulta.")
            if not self.parcel:
                raise ProdesError("Prepare o recorte primeiro.")
            reviewed_any = any(self.table.cellWidget(index, 6).isChecked() for index in range(len(self.rows)))
            self.map_rasters = self.build_rasters(required=reviewed_any)
            if reviewed_any and len({box.currentData() for box in self.images}) != 3:
                raise ProdesError("Escolha três imagens distintas. Composições da mesma cena não substituem datas diferentes.")
            dates = [widget.date().toString("yyyy-MM-dd") for widget in self.dates]
            sources = [QgsProject.instance().mapLayer(box.currentData()) for box in self.images]
            for index, source in enumerate(sources):
                if source is None:
                    continue
                acquired = str(source.customProperty("catalogo_multiespectral_data", ""))
                if acquired and acquired != dates[index]:
                    raise ProdesError("A data declarada difere da aquisição registrada no catálogo: " + source.name())
                keys = str(source.customProperty("catalogo_multiespectral_bandas", "")).split(",")
                bands = [spin.value() for spin in self.bands[index]]
                if len(keys) == source.bandCount() and len(keys) >= 3:
                    mapped = [keys[band - 1] for band in bands]
                    if mapped not in (["swir16", "nir08", "red"], ["B11", "B08", "B04"]):
                        raise ProdesError("Selecione uma composição PRODES (SWIR1/NIR/vermelho) do catálogo para os mapas: " + source.name())
            scene_ids = [layer.customProperty("catalogo_multiespectral_cena", "") for layer in sources if layer]
            if reviewed_any and any(scene and scene_ids.count(scene) > 1 for scene in scene_ids):
                raise ProdesError("Há composições da mesma cena no conjunto. Selecione datas distintas.")
            for index, item in enumerate(self.rows):
                observations = [self.table.cellWidget(index, column).currentData() for column in (3, 4, 5)]
                result = evaluate(item, observations, dates, self.table.cellWidget(index, 6).isChecked(),
                    self.annual.isChecked(), self.car_boundary.isChecked())
                item.update(result)
                item["notes"] = self.table.cellWidget(index, 7).text()
                self.table.setItem(index, 8, QTableWidgetItem(item["status"]))
            self.context = {"Imóvel": self.name.text().strip() or self.parcel.name(), "CAR": self.car.text().strip() or "Não informado",
                "Revisor": self.reviewer.text().strip() or "Não informado", "Fonte PRODES": self.source_note,
                "Exportação / análise UTC": datetime.now(timezone.utc).isoformat(), "Ano PRODES": "Todos" if self.all_years.isChecked() else self.year.value(),
                "Incremento por bioma confirmado": self.annual.isChecked(), "Regras": RULE_VERSION,
                "SRC de cálculo": "EPSG:4326; área geodésica GRS80", **self.prepared_details}
            for index, source in enumerate(sources):
                self.context["Imagem {}".format(index + 1)] = (
                    source.name() + " | " + dates[index] + " | índices RGB=" + "/".join(str(spin.value()) for spin in self.bands[index])
                    + " | bandas catálogo=" + str(source.customProperty("catalogo_multiespectral_bandas", "não informadas"))
                    if source else "Ausente: data exibida no formulário não constitui evidência")
            self.report.setHtml(report_html(self.context, self.rows))
            self.export_button.setEnabled(True)
            self.tabs.setCurrentIndex(3)
            self.info.setText("Avaliação assistida concluída. Confira as justificativas e exporte o pacote.")
        except Exception as exc:
            self.error(exc)

    def map_date(self, index):
        if self.map_evidence:
            return QDate.fromString(self.map_evidence[index]["date"], "yyyy-MM-dd")
        if index < 3:
            return self.dates[index].date()
        historic = QgsProject.instance().mapLayer(self.historical_box.currentData())
        return QDate.fromString(str(historic.customProperty("catalogo_multiespectral_data", "")), "yyyy-MM-dd") if historic else QDate()

    def export_map(self, raster, index, directory, polygon_index=None):
        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        layout.initializeDefaults()
        layout.pageCollection().pages()[0].setPageSize(QgsLayoutSize(297, 210))
        title = QgsLayoutItemLabel(layout)
        title.setFont(QFont("Arial",14,QFont.Weight.Bold))
        title.setText("ANÁLISE TEMPORAL — " + self.context["Imóvel"][:42] + (" · Polígono {} / {}".format(polygon_index+1, self.rows[polygon_index]["year"]) if polygon_index is not None else ""))
        layout.addLayoutItem(title)
        title.attemptMove(QgsLayoutPoint(10, 6))
        title.attemptResize(QgsLayoutSize(228, 10))
        map_item = QgsLayoutItemMap(layout)
        layout.addLayoutItem(map_item)
        map_item.attemptMove(QgsLayoutPoint(10, 20))
        map_item.attemptResize(QgsLayoutSize(277, 158))
        center=self.parcel.extent().center()
        zone=max(1,min(60,int((center.x()+180)/6)+1))
        map_crs=QgsCoordinateReferenceSystem('EPSG:'+str((32700 if center.y()<0 else 32600)+zone))
        transform=QgsCoordinateTransform(self.parcel.crs(),map_crs,project)
        map_item.setCrs(map_crs)
        focus = self.clipped
        if polygon_index is not None:
            focus = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "Polígono em análise", "memory")
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromWkt(self.analysis_geometries[polygon_index]))
            if not focus.dataProvider().addFeatures([feature])[0]:
                raise ProdesError("Não foi possível destacar o polígono no mapa.")
            focus.updateExtents()
            outline(focus, "220,30,45,255", 1.0)
        map_item.setLayers([layer for layer in (self.parcel, focus, self.consolidated_preview, self.original, raster) if layer is not None])
        map_item.setKeepLayerSet(True)
        extent=transform.transformBoundingBox(focus.extent() if polygon_index is not None else self.parcel.extent())
        if polygon_index is not None:
            margin=max(150, max(extent.width(),extent.height())*.2)
            extent=QgsRectangle(extent.xMinimum()-margin,extent.yMinimum()-margin,extent.xMaximum()+margin,extent.yMaximum()+margin)
        else:extent.scale(1.5)
        map_item.zoomToExtent(extent)
        overview=QgsLayoutItemMap(layout);layout.addLayoutItem(overview)
        overview.attemptMove(QgsLayoutPoint(220,22));overview.attemptResize(QgsLayoutSize(64,45))
        overview.setCrs(map_crs);overview.setLayers([self.parcel,focus]);overview.setKeepLayerSet(True)
        overview.setBackgroundEnabled(True);overview.setBackgroundColor(QColor('white'));overview.setFrameEnabled(True)
        whole=transform.transformBoundingBox(self.parcel.extent());whole.scale(1.2);overview.zoomToExtent(whole)
        north=QgsLayoutItemPicture(layout);layout.addLayoutItem(north)
        north.attemptMove(QgsLayoutPoint(12,23));north.attemptResize(QgsLayoutSize(12,20))
        north.setPicturePath(os.path.join(os.path.dirname(__file__),'north.svg'))
        date_label=QgsLayoutItemLabel(layout);layout.addLayoutItem(date_label)
        date_label.setFont(QFont('Arial',11,QFont.Weight.Bold))
        date_label.setText(self.map_date(index).toString('dd/MM/yyyy'))
        date_label.attemptMove(QgsLayoutPoint(242,6));date_label.attemptResize(QgsLayoutSize(45,10))
        footer = QgsLayoutItemLabel(layout)
        footer.setText("{} | N da grade | Imóvel: azul; PRODES: laranja; recorte: vermelho; consolidada: roxo\n"
            "SRC {} | Fonte: INPE/TerraBrasilis + Landsat USGS/NASA | Cena: {} | RGB: {}\nPixels nativos, sem suavização; contraste de reflectância 0.02–0.45 na investigação. Análise experimental para revisão técnica.".format(
                self.map_date(index).toString("dd/MM/yyyy"), map_crs.authid(), raster.name()[:65],
                "SWIR1/NIR/vermelho" if self.map_evidence else "/".join(str(spin.value()) for spin in self.bands[index]) if index < 3 else "SWIR1/NIR/vermelho (referência pré-marco)"))
        footer.setFont(QFont("Arial",8))
        layout.addLayoutItem(footer)
        footer.attemptMove(QgsLayoutPoint(10, 180))
        footer.attemptResize(QgsLayoutSize(277, 24))
        scale = QgsLayoutItemScaleBar(layout)
        layout.addLayoutItem(scale)
        scale.setStyle("Single Box")
        scale.setUnits(QgsUnitTypes.DistanceUnit.DistanceMeters)
        scale.setUnitsPerSegment(100)
        scale.setUnitLabel("m")
        scale.setFont(QFont("Arial",8))
        scale.setLinkedMap(map_item)
        scale.applyDefaultSize()
        scale.attemptMove(QgsLayoutPoint(12, 161))
        filename = "mapa_{}.png".format(index + 1) if polygon_index is None else "poligono_{}_imagem_{}.png".format(polygon_index+1,index+1)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = self.map_dpi.value()
        result = QgsLayoutExporter(layout).exportToImage(os.path.join(directory, filename), settings)
        if result != QgsLayoutExporter.ExportResult.Success:
            raise ProdesError("Falha ao exportar o mapa: " + filename)
        return filename

    def open_package(self):
        if self.last_export and os.path.isdir(self.last_export):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_export))

    def export(self, directory=None):
        automatic=isinstance(directory,str)
        if not automatic:
            directory = QFileDialog.getExistingDirectory(self, "Pasta para o pacote da análise")
        if not directory:
            return
        # A new subdirectory prevents accidental overwrite of an existing analysis.
        directory = tempfile.mkdtemp(prefix="Analise_PRODES_", dir=directory)
        try:
            self.info.setText("Exportando mapas e relatório…")
            maps=[]
            if self.generated_maps:
                for value in self.generated_maps:
                    target=os.path.join(directory,os.path.basename(value['filename']))
                    shutil.copy2(value['filename'],target);maps.append(dict(value,filename=target))
            else:maps=self.make_report_maps(directory)
            receipt=self.analysis_payload.get('investigation') if self.analysis_payload else None
            if receipt:
                for name in ('events.jsonl','session.json'):
                    shutil.copy2(os.path.join(receipt['directory'],name),os.path.join(directory,name))
            if self.analysis_payload:
                with open(os.path.join(directory,'selecao_imagens.csv'),'w',encoding='utf-8-sig',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=['uuid','scene_id','date','platform','qa_complete','coverage','pixels','usable','selected','reason'])
                    writer.writeheader()
                    for row in self.rows:
                        for value in row.get('agent',{}).get('selection',[]):writer.writerow({key:value.get(key,'') for key in writer.fieldnames})
                with open(os.path.join(directory,'investigacao.json'),'w',encoding='utf8') as stream:
                    json.dump({'investigation':receipt,'dossiers':[r.get('agent',{}) for r in self.rows]},stream,ensure_ascii=False,indent=2,allow_nan=False)
            gpkg = os.path.join(directory, "evidencias.gpkg")
            vectors = [self.parcel, self.original, self.clipped]
            if self.consolidated_preview is not None:
                vectors.append(self.consolidated_preview)
            for index, layer in enumerate(vectors):
                options = QgsVectorFileWriter.SaveVectorOptions()
                options.driverName = "GPKG"
                options.layerName = ("imovel", "prodes_original", "prodes_recorte", "consolidada_tecnica")[index]
                options.fileEncoding = "UTF-8"
                options.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile if index == 0
                    else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer)
                result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, gpkg, QgsProject.instance().transformContext(), options)
                if result[0] != QgsVectorFileWriter.WriterError.NoError:
                    raise ProdesError("Falha no GeoPackage: " + str(result))
            text = report_html(self.context, self.rows, maps)
            with open(os.path.join(directory, "relatorio.html"), "w", encoding="utf-8") as stream:
                stream.write(text)
            document = QTextDocument()
            document.setBaseUrl(QUrl.fromLocalFile(directory + os.sep))
            document.setHtml(text)
            self.attach_map_resources(document, maps)
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(os.path.join(directory, "relatorio.pdf"))
            print_document = getattr(document, "print", None) or getattr(document, "print_")
            print_document(printer)
            pdf = printer.outputFileName()
            if not os.path.isfile(pdf) or os.path.getsize(pdf) == 0:
                raise ProdesError("Não foi possível gerar o PDF.")
            hashes = {}
            for filename in os.listdir(directory):
                with open(os.path.join(directory, filename), "rb") as stream:
                    digest = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                hashes[filename] = digest.hexdigest()
            manifest = {"version": "3.3.0", "rules": CONTEST_RULE_VERSION if self.analysis_payload else RULE_VERSION, "context": self.context,
                "results": self.rows, "sha256": hashes, "raster_files_included": False,
                "automatic_inputs": self.analysis_payload["images"] if self.analysis_payload else None,
                "historical_input": self.analysis_payload.get("historical_image") if self.analysis_payload else None,
                "acquisition_groups": self.analysis_payload.get("acquisition_groups") if self.analysis_payload else None,
                "limitations": "Triagem preliminar própria; não decide falso PRODES nem legalidade. Os rasters permanecem no projeto/acervo e não estão incluídos neste pacote."}
            with open(os.path.join(directory, "manifesto.json"), "w", encoding="utf-8") as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
            self.last_export=directory;self.open_package_button.setEnabled(True)
            self.info.setText("Pacote exportado: " + directory)
            if not automatic:QMessageBox.information(self, "Exportação concluída", "Relatório, mapas, dados vetoriais e manifesto em:\n" + directory)
        except Exception as exc:
            self.error("Exportação incompleta em {}: {}".format(directory, exc))

    def closeEvent(self, event):
        if self.maps_in_progress:
            self.cancel();event.ignore();return
        if self.job and self.job.isRunning():
            self.cancel()
            event.ignore()
            return
        self.canvas.stopRendering()
        self.canvas.setLayers([])
        super().closeEvent(event)
