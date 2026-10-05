# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""QGIS UI for anonymous Landsat and Sentinel image retrieval."""
import os
import logging
import json
import math
from datetime import date

from qgis.PyQt.QtCore import QDate, QSize, Qt, QThread, QUrl, QStandardPaths, pyqtSignal
from qgis.PyQt.QtGui import QColor, QIcon, QPixmap
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QFileDialog, QSlider)
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsProject, QgsRasterLayer, QgsVectorLayer, QgsWkbTypes,
                       QgsMultiBandColorRenderer, QgsContrastEnhancement,
                       QgsColorRampShader, QgsRasterShader,
                       QgsSingleBandPseudoColorRenderer, QgsSettings, QgsGeometry,
                       QgsCubicRasterResampler, QgsBilinearRasterResampler)
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsRubberBand
from .archive import LocalArchive
from .stac import (COLLECTIONS, CatalogError, PublicCatalog, available_bands,
                   band_label, default_rgb_keys, natural_rgb_keys, ndvi_keys,
                   preview_url, prodes_label, PRESETS, preset_keys, index_keys, slc_gap_scene)

class Job(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, action, **kwargs):
        super().__init__()
        self.action, self.args, self.stopping = action, kwargs, False

    def cancel(self):
        self.stopping = True

    def run(self):
        client = PublicCatalog(cancelled=lambda: self.stopping)
        try:
            if self.action == "search":
                self.status.emit("Consultando imagens públicas…")
                data = client.search(**self.args)
            elif self.action == "local":
                data = (self.args["archive"].search(self.args["collections"],
                        self.args["start"], self.args["end"]), None)
            elif self.action == "sync":
                data = self.args["archive"].sync(client, self.args["collections"],
                        self.args["start"], self.args["end"], self.status.emit)
            else:
                archive = self.args["archive"]
                item = self.args["item"]
                archive.remember(item)
                data = client.download_scene(item,
                    archive.scene_folder(item), archive.rect, archive.target_crs,
                    self.status.emit, self.args["rgb_keys"],
                    self.args.get("product", "rgb"), self.args.get("offline", False),
                    self.args.get("force_download", False))
                archive.remember(item, data[1])
            if not self.stopping:
                self.result.emit(data)
        except Exception as exc:
            if not self.stopping:
                self.failed.emit(str(exc))


class PreviewDialog(QDialog):
    """Preview real georeferenced pixels, with a cloned property outline."""
    def __init__(self, raster, property_layer, description, iface, offline, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prévia georreferenciada — confira a área antes de importar")
        screen = self.screen()
        available = screen.availableGeometry() if screen else None
        self.resize(min(1280, available.width() - 60) if available else 1280,
                    min(800, available.height() - 80) if available else 800)
        self.raster = raster
        layout = QVBoxLayout(self)
        text = QLabel(description + "\nContorno azul: limite do imóvel. Use a roda do mouse para zoom e arraste para mover.")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.canvas = QgsMapCanvas(self)
        self.canvas.setCanvasColor(QColor("#17242e"))
        self.canvas.enableAntiAliasing(True)
        self.canvas.setDestinationCrs(raster.crs())
        self.canvas.setLayers([raster])
        self.pan = QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(self.pan)
        layout.addWidget(self.canvas, 1)
        self.outlines = []
        transform = QgsCoordinateTransform(property_layer.crs(), raster.crs(), QgsProject.instance())
        for feature in property_layer.getFeatures():
            if not feature.hasGeometry():
                continue
            geometry = QgsGeometry(feature.geometry())
            geometry.transform(transform)
            outline = QgsRubberBand(self.canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
            outline.setToGeometry(geometry, None)
            outline.setStrokeColor(QColor("#48b7ff"))
            outline.setFillColor(QColor(0, 0, 0, 0))
            outline.setWidth(3)
            self.outlines.append(outline)
        toolbar = QHBoxLayout()
        limits = QCheckBox("Mostrar limite"); limits.setChecked(True)
        limits.toggled.connect(lambda visible: [outline.setVisible(visible) for outline in self.outlines])
        toolbar.addWidget(limits)
        frame = QPushButton("Enquadrar área")
        frame.clicked.connect(self.frame_area)
        toolbar.addWidget(frame)
        toolbar.addWidget(QLabel("Comparar com:"))
        self.reference = QComboBox()
        self.reference.addItem("Sem referência", None)
        self.references = {}
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsRasterLayer) or not layer.isValid():
                continue
            # Offline mode never offers a reference requiring a remote provider.
            if offline and (layer.providerType() != "gdal" or not os.path.isfile(layer.source()) or
                    os.path.splitext(layer.source())[1].lower() not in (".tif", ".tiff", ".jp2", ".png", ".jpg")):
                continue
            self.references[layer.id()] = layer
            self.reference.addItem(layer.name(), layer.id())
        toolbar.addWidget(self.reference, 1)
        toolbar.addWidget(QLabel("Opacidade da cena:"))
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100); self.opacity.setValue(100)
        self.opacity.setMaximumWidth(160)
        toolbar.addWidget(self.opacity)
        self.reference.currentIndexChanged.connect(self.update_layers)
        self.opacity.valueChanged.connect(self.update_layers)
        layout.addLayout(toolbar)
        row = QHBoxLayout()
        back = QPushButton("Voltar para escolher outra cena")
        back.clicked.connect(self.reject)
        use = QPushButton("Importar esta composição")
        use.clicked.connect(self.accept)
        row.addWidget(back); row.addStretch(); row.addWidget(use)
        layout.addLayout(row)
        self.frame_area()

    def frame_area(self):
        self.canvas.setExtent(self.raster.extent())
        self.canvas.refresh()

    def update_layers(self):
        reference = self.references.get(self.reference.currentData())
        self.raster.renderer().setOpacity(self.opacity.value() / 100.0)
        self.canvas.setLayers([self.raster, reference] if reference else [self.raster])
        self.canvas.refresh()

    def done(self, result):
        # Opacity is a comparison aid; imported imagery keeps the normal style.
        self.raster.renderer().setOpacity(1.0)
        self.canvas.stopRendering()
        self.canvas.setLayers([])
        super().done(result)


class CatalogDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Catálogo Multiespectral | Imagens Orbitais")
        self.resize(1180, 850)
        self.job, self.next_link, self.active_scene, self.search_params = None, None, None, None
        self.scenes = []
        self.archive = None
        self.search_layer_id = None
        self.band_scene_id = None
        self.preview_manager = QNetworkAccessManager(self)
        self.preview_queue = []
        self.preview_active = 0
        self.preview_generation = 0
        self.preview_cache = {}
        self.preview_replies = set()
        layout = QVBoxLayout(self)
        intro = QLabel("Selecione o imóvel. A busca exibe apenas cenas com menos de 20% de nuvens. Não requer conta.")
        intro.setWordWrap(True); layout.addWidget(intro)
        box = QGroupBox("Pesquisar imagens"); form = QFormLayout(box)
        self.layer_box = QComboBox(); self.refresh = QPushButton("Atualizar camadas")
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.layer_box, 1); h.addWidget(self.refresh)
        form.addRow("Limite do imóvel:", row)
        self.offline = QCheckBox("Modo offline — usar apenas o acervo local")
        form.addRow("Fonte:", self.offline)
        self.archive_path = QgsSettings().value("catalogo_multiespectral/acervo", "", type=str)
        if not self.archive_path:
            documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or os.path.expanduser("~")
            self.archive_path = os.path.join(documents, "Catalogo_Multiespectral_Acervo")
        self.archive_label = QLabel(self.archive_path)
        self.archive_label.setWordWrap(True)
        self.choose_archive = QPushButton("Escolher pasta")
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.archive_label, 1); h.addWidget(self.choose_archive)
        form.addRow("Acervo permanente:", row)
        self.landsat = QCheckBox(COLLECTIONS["landsat-c2-l2"]); self.landsat.setChecked(True)
        self.sentinel = QCheckBox(COLLECTIONS["sentinel-2-l2a"]); self.sentinel.setChecked(True)
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.landsat); h.addWidget(self.sentinel); h.addStretch()
        form.addRow("Satélites:", row)
        self.hide_slc = QCheckBox("Ocultar Landsat 7 com lacunas do sensor (SLC-off)")
        self.hide_slc.setToolTip("Cenas posteriores a maio de 2003 têm lacunas reais. Desmarque para incluí-las e refaça a busca.")
        form.addRow("Integridade da cena:", self.hide_slc)
        self.year = QComboBox()
        self.year.addItem("Período personalizado", None)
        self.year.addItem("Todo o histórico (1982–hoje)", -1)
        for year in range(date.today().year, 1981, -1):
            self.year.addItem(str(year), year)
        self.year.setCurrentIndex(2)
        form.addRow("Ir para o ano:", self.year)
        self.start = QDateEdit(); self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("dd/MM/yyyy"); self.start.setDate(QDate(date.today().year - 1, 1, 1))
        self.end = QDateEdit(); self.end.setCalendarPopup(True)
        self.end.setDisplayFormat("dd/MM/yyyy"); self.end.setDate(QDate.currentDate())
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("De")); h.addWidget(self.start)
        h.addWidget(QLabel("até")); h.addWidget(self.end); h.addStretch()
        form.addRow("Aquisição:", row); layout.addWidget(box)
        self.year.currentIndexChanged.connect(self.year_changed)
        self.search = QPushButton("Buscar imagens com nuvens < 20%")
        self.more = QPushButton("Próximas cenas"); self.more.setEnabled(False)
        self.sync_button = QPushButton("Baixar / atualizar todas as cenas do período")
        row = QHBoxLayout(); row.addWidget(self.search); row.addWidget(self.more)
        row.addWidget(self.sync_button); row.addStretch()
        layout.addLayout(row)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Miniatura", "Ano", "Data", "Satélite", "Nuvens", "Cena", "Acervo local"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setIconSize(QSize(152, 110))
        self.table.setColumnWidth(0, 165)
        self.table.setColumnWidth(1, 65)
        self.table.setColumnWidth(2, 105)
        self.table.setColumnWidth(3, 115)
        self.table.setColumnWidth(4, 80)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(6, 135)
        self.preview_large = QLabel("Selecione uma cena para ver a prévia ampliada")
        self.preview_large.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_large.setWordWrap(True)
        self.preview_large.setMinimumWidth(300)
        self.preview_large.setMaximumWidth(340)
        self.preview_large.setStyleSheet("background:#1b2732;color:white;border-radius:6px;padding:8px;")
        content = QHBoxLayout(); content.addWidget(self.table, 1); content.addWidget(self.preview_large)
        layout.addLayout(content, 1)
        band_box = QGroupBox("Composição RGB — escolha as bandas")
        band_layout = QVBoxLayout(band_box)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Opção de bandas:"))
        self.preset = QComboBox()
        self.preset.setMinimumContentsLength(28)
        preset_row.addWidget(self.preset, 1)
        band_layout.addLayout(preset_row)
        band_row = QHBoxLayout()
        band_layout.addLayout(band_row)
        self.rgb_boxes = []
        for label in ("Vermelho (R)", "Verde (G)", "Azul (B)"):
            band_row.addWidget(QLabel(label))
            combo = QComboBox(); combo.setMinimumWidth(128)
            self.rgb_boxes.append(combo); band_row.addWidget(combo)
        self.false_color = QPushButton("PRODES — INPE")
        self.false_color.setToolTip("Composição principal do PRODES Amazônia: TM/ETM+ 5–4–3; OLI 6–5–4; Sentinel-2 11–8–4. SWIR1 / NIR / vermelho.")
        self.natural_color = QPushButton("Cor natural")
        band_row.addWidget(self.false_color); band_row.addWidget(self.natural_color)
        layout.addWidget(band_box)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.false_color.clicked.connect(lambda: self.preset.setCurrentIndex(self.preset.findData("prodes")))
        self.natural_color.clicked.connect(lambda: self.preset.setCurrentIndex(self.preset.findData("natural")))
        self.smooth_rgb = QCheckBox("Suavizar pixels na visualização RGB")
        self.smooth_rgb.setChecked(True)
        self.smooth_rgb.setToolTip("Suavização apenas na tela e nos mapas. Desmarque para inspecionar os pixels originais. Não aumenta o detalhe do satélite nem altera o NDVI.")
        layout.addWidget(self.smooth_rgb)
        self.repair = QCheckBox("Baixar novamente as bandas desta cena (recuperar acervo)")
        self.repair.setToolTip("Ignora as bandas em cache e baixa novos recortes. Requer internet; não preenche lacunas reais do sensor.")
        layout.addWidget(self.repair)
        self.import_button = QPushButton("Ver prévia no mapa e importar RGB")
        self.import_button.setEnabled(False)
        self.ndvi_button = QPushButton("Calcular NDVI da cena")
        self.ndvi_button.setEnabled(False)
        self.cancel_button = QPushButton("Cancelar tarefa"); self.cancel_button.setEnabled(False)
        row = QHBoxLayout(); row.addWidget(self.import_button)
        row.addWidget(self.ndvi_button); row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.info = QLabel("A prévia abre antes da importação. Bandas baixadas ficam no acervo para reutilização offline.")
        self.info.setWordWrap(True); layout.addWidget(self.info)
        self.refresh.clicked.connect(self.refresh_layers)
        self.search.clicked.connect(self.search_first)
        self.choose_archive.clicked.connect(self.select_archive_folder)
        self.sync_button.clicked.connect(self.sync_archive)
        self.offline.toggled.connect(self.source_changed)
        self.more.clicked.connect(self.search_more)
        self.import_button.clicked.connect(self.import_scene)
        self.ndvi_button.clicked.connect(self.import_ndvi)
        self.cancel_button.clicked.connect(self.cancel_job)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.year_changed()
        self.refresh_layers()

    def year_changed(self):
        year = self.year.currentData()
        if year == -1:
            self.start.setDate(QDate(1982, 1, 1))
            self.end.setDate(QDate.currentDate())
        elif year:
            self.start.setDate(QDate(year, 1, 1))
            self.end.setDate(QDate.currentDate() if year == date.today().year else QDate(year, 12, 31))

    def reset_results(self):
        self.preview_generation += 1
        self.preview_queue.clear()
        self.scenes = []
        self.next_link = None
        self.band_scene_id = None
        self.table.setRowCount(0)
        self.preview_large.clear()
        self.more.setEnabled(False)
        self.update_import_button()

    def source_changed(self):
        self.preview_generation += 1
        self.preview_queue.clear()
        for reply in list(self.preview_replies):
            reply.abort()
        self.reset_results()
        self.sync_button.setEnabled(not self.offline.isChecked() and self.job is None)
        self.repair.setEnabled(not self.offline.isChecked())
        if self.offline.isChecked():
            self.repair.setChecked(False)
        self.search.setText("Buscar no acervo local" if self.offline.isChecked() else "Buscar imagens com nuvens < 20%")

    def select_archive_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pasta do acervo local", self.archive_path)
        if folder:
            self.archive_path = folder
            QgsSettings().setValue("catalogo_multiespectral/acervo", folder)
            self.archive_label.setText(folder)
            self.archive = None
            self.reset_results()

    def current_search(self):
        if self.start.date() > self.end.date():
            raise CatalogError("A data inicial precisa ser anterior à data final.")
        rect = self.area()
        layer = QgsProject.instance().mapLayer(self.layer_box.currentData())
        crs = layer.crs().authid() or layer.crs().toWkt()
        self.archive = LocalArchive(self.archive_path, rect, crs, allow_legacy=self.offline.isChecked())
        self.search_layer_id = layer.id()
        return {"collections": self.collections(), "rect": rect,
                "start": self.start.date().toString("yyyy-MM-dd"),
                "end": self.end.date().toString("yyyy-MM-dd")}

    def sync_archive(self):
        if self.job or self.offline.isChecked():
            return
        try:
            params = self.current_search()
        except Exception as exc:
            QMessageBox.warning(self, "Acervo local", str(exc)); return
        self.search_params = params
        self.reset_results()
        self.run_job("sync", self.got_sync, archive=self.archive,
                     collections=params["collections"], start=params["start"], end=params["end"])

    def got_sync(self, result):
        self.got_scenes((result["items"], None))
        self.info.setText("Acervo atualizado: {} cenas completas; {} com falhas. Pasta: {}".format(
            result["completed"], len(result["errors"]), self.archive_path))
        if result["errors"]:
            QMessageBox.warning(self, "Atualização parcial do acervo",
                "Os arquivos concluídos foram mantidos. Atualize novamente para tentar as bandas faltantes.\n\n" +
                "\n".join(result["errors"][:8]))

    def selection_changed(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.scenes):
            self.preview_large.setText("Selecione uma cena para ver a prévia ampliada")
            self.band_scene_id = None
            self.update_import_button()
            return
        scene = self.scenes[row]
        self.false_color.setText(prodes_label(scene))
        if self.band_scene_id != scene.get("id"):
            self.band_scene_id = scene.get("id")
            for combo in self.rgb_boxes:
                combo.clear()
                for key, asset in available_bands(scene):
                    combo.addItem(band_label(key, asset), key)
            self.preset.blockSignals(True)
            self.preset.clear()
            for identifier, label, keys in PRESETS:
                selected = preset_keys(scene, identifier)
                if selected:
                    bands = dict(available_bands(scene))
                    names = [str((bands[key].get("eo:bands") or [{}])[0].get("name", key)) for key in selected]
                    self.preset.addItem(label + " — " + " / ".join(names), identifier)
            for product in ("ndvi", "nbr"):
                if index_keys(scene, product):
                    self.preset.addItem(product.upper() + " — índice espectral", product)
            self.preset.addItem("Personalizada — escolher R, G e B", "custom")
            self.preset.blockSignals(False)
            self.apply_preset()
        self.update_import_button()
        url = preview_url(scene, 560)
        local = os.path.join(self.archive.scene_folder(scene), "miniatura_560.png") if self.archive else ""
        if local and os.path.isfile(local):
            self.show_large(QPixmap(local))
            return
        if self.offline.isChecked():
            self.preview_large.setText("{}\nClique em ‘Ver prévia no mapa’ para conferir a cena com o limite do imóvel.".format(
                self.archive.status(scene)))
            return
        self.preview_large.setText("Carregando prévia…")
        if url in self.preview_cache:
            self.show_large(self.preview_cache[url])
        elif url:
            self.preview_queue.insert(0, (row, url, self.preview_generation, True))
            self.pump_previews()

    def apply_preset(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.scenes):
            return
        product = self.preset.currentData()
        if product not in ("ndvi", "nbr", "custom"):
            self.set_rgb(preset_keys(self.scenes[row], product))
        is_index = product in ("ndvi", "nbr")
        for combo in self.rgb_boxes:
            combo.setEnabled(not is_index)
        self.import_button.setText("Ver prévia no mapa e importar " + (product.upper() if is_index else "RGB"))
        self.update_import_button()

    def set_rgb(self, keys):
        if len(keys) != 3:
            return
        for combo, key in zip(self.rgb_boxes, keys):
            index = combo.findData(key)
            if index >= 0:
                combo.setCurrentIndex(index)

    def show_large(self, pixmap):
        if not pixmap.isNull():
            self.preview_large.setPixmap(pixmap.scaled(320, 320,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def pump_previews(self):
        if self.offline.isChecked():
            self.preview_queue.clear()
            return
        while self.preview_active < 4 and self.preview_queue:
            row, url, generation, large = self.preview_queue.pop(0)
            if generation != self.preview_generation:
                continue
            if url in self.preview_cache:
                self.apply_preview(row, url, generation, large, self.preview_cache[url])
                continue
            reply = self.preview_manager.get(QNetworkRequest(QUrl(url)))
            self.preview_replies.add(reply)
            self.preview_active += 1
            reply.finished.connect(lambda r=reply, idx=row, u=url, gen=generation, big=large:
                self.preview_finished(r, idx, u, gen, big))

    def preview_finished(self, reply, row, url, generation, large):
        self.preview_active -= 1
        self.preview_replies.discard(reply)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            pixmap.loadFromData(reply.readAll())
            if not pixmap.isNull():
                self.preview_cache[url] = pixmap
                if generation == self.preview_generation and self.archive and row < len(self.scenes):
                    folder = self.archive.scene_folder(self.scenes[row])
                    try:
                        os.makedirs(folder, exist_ok=True)
                        pixmap.save(os.path.join(folder, "miniatura_{}.png".format(560 if large else 180)))
                    except OSError:
                        logging.getLogger(__name__).warning("Não foi possível salvar a miniatura no acervo.")
                self.apply_preview(row, url, generation, large, pixmap)
        reply.deleteLater()
        self.pump_previews()

    def apply_preview(self, row, url, generation, large, pixmap):
        if generation != self.preview_generation:
            return
        if large:
            if row == self.table.currentRow():
                self.show_large(pixmap)
        elif row < self.table.rowCount():
            item = self.table.item(row, 0)
            if item:
                item.setText("")
                item.setIcon(QIcon(pixmap.scaled(152, 110,
                    Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))

    def refresh_layers(self):
        current = self.layer_box.currentData(); self.layer_box.clear()
        layers = [layer for layer in QgsProject.instance().mapLayers().values()
                  if isinstance(layer, QgsVectorLayer) and layer.isValid() and
                  layer.geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry]
        for layer in sorted(layers, key=lambda layer: layer.name().lower()):
            self.layer_box.addItem(layer.name(), layer.id())
        index = self.layer_box.findData(current) if current else -1
        if index >= 0: self.layer_box.setCurrentIndex(index)

    def area(self):
        layer = QgsProject.instance().mapLayer(self.layer_box.currentData())
        if not layer or not layer.isValid() or layer.featureCount() == 0:
            raise CatalogError("Selecione uma camada poligonal do imóvel com feições.")
        if not layer.crs().isValid():
            raise CatalogError("Defina o SRC da camada do imóvel antes da busca.")
        transform = QgsCoordinateTransform(layer.crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
        extent = transform.transformBoundingBox(layer.extent())
        return (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())

    def collections(self):
        chosen = []
        if self.landsat.isChecked(): chosen.append("landsat-c2-l2")
        if self.sentinel.isChecked(): chosen.append("sentinel-2-l2a")
        if not chosen: raise CatalogError("Selecione Landsat, Sentinel-2 ou ambos.")
        return chosen

    def run_job(self, action, callback, **kwargs):
        if self.job: return
        self.job = Job(action, **kwargs)
        self.job.status.connect(self.info.setText)
        self.job.result.connect(callback)
        self.job.failed.connect(lambda message: QMessageBox.warning(self, "Imagens públicas", message))
        self.job.finished.connect(self.finished_job)
        self.set_busy(True); self.job.start()

    def finished_job(self):
        self.job.deleteLater(); self.job = None; self.set_busy(False)

    def set_busy(self, busy):
        for widget in (self.layer_box, self.refresh, self.landsat, self.sentinel,
                       self.start, self.end, self.year, self.search, self.more,
                       self.import_button, self.ndvi_button,
                       self.offline, self.choose_archive, self.sync_button,
                       self.false_color, self.natural_color, self.smooth_rgb, self.preset, self.hide_slc, self.repair,
                       *self.rgb_boxes, self.table):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        if not busy:
            self.more.setEnabled(bool(self.next_link))
            self.apply_preset()
            self.sync_button.setEnabled(not self.offline.isChecked())
            self.repair.setEnabled(not self.offline.isChecked())

    def update_import_button(self):
        row = self.table.currentRow()
        ready = 0 <= row < len(self.scenes) and self.job is None
        self.import_button.setEnabled(ready and
            all(combo.currentData() for combo in self.rgb_boxes))
        self.ndvi_button.setEnabled(ready and bool(ndvi_keys(self.scenes[row])) if ready else False)

    def cancel_job(self):
        if self.job:
            self.job.cancel(); self.info.setText("Cancelando…")

    def search_first(self):
        try:
            params = self.current_search()
        except Exception as exc:
            QMessageBox.warning(self, "Imagens públicas", str(exc)); return
        self.search_params = params
        self.reset_results()
        if self.offline.isChecked():
            self.run_job("local", self.got_scenes, archive=self.archive,
                         collections=params["collections"], start=params["start"], end=params["end"])
        else:
            self.run_job("search", self.got_scenes, **params)

    def search_more(self):
        if self.next_link and self.search_params and not self.offline.isChecked():
            self.run_job("search", self.got_scenes, next_link=self.next_link,
                         **self.search_params)

    def got_scenes(self, response):
        scenes, self.next_link = response
        if self.archive and not self.offline.isChecked():
            self.archive.remember_many(scenes)
        seen = {(item.get("collection"), item.get("id")) for item in self.scenes}
        for scene in scenes:
            if self.hide_slc.isChecked() and slc_gap_scene(scene):
                continue
            identity = (scene.get("collection"), scene.get("id"))
            if identity in seen:
                continue
            seen.add(identity)
            props = scene.get("properties", {})
            acquired = str(props.get("datetime", ""))[:10]
            cloud = props.get("eo:cloud_cover")
            row = self.table.rowCount(); self.table.insertRow(row)
            fields = [acquired[:4], acquired,
                      str(props.get("platform") or scene.get("collection", "")) + (" ⚠ SLC-off" if slc_gap_scene(scene) else ""),
                      "{:.1f}%".format(float(cloud)), str(scene.get("id", ""))]
            self.table.setRowHeight(row, 118)
            self.table.setItem(row, 0, QTableWidgetItem("Ver no mapa" if self.offline.isChecked() else "Carregando…"))
            for col, value in enumerate(fields, 1):
                self.table.setItem(row, col, QTableWidgetItem(value))
            self.scenes.append(scene)
            self.table.setItem(row, 6, QTableWidgetItem(self.archive.status(scene)))
            url = preview_url(scene, 180)
            local = os.path.join(self.archive.scene_folder(scene), "miniatura_180.png")
            if os.path.isfile(local):
                self.apply_preview(row, url, self.preview_generation, False, QPixmap(local))
            elif url and not self.offline.isChecked():
                self.preview_queue.append((row, url, self.preview_generation, False))
        self.pump_previews()
        self.more.setEnabled(bool(self.next_link))
        self.info.setText("{} cenas com menos de 20% de nuvens listadas. {}".format(
            len(self.scenes), "Há mais resultados." if self.next_link else "Fim da busca."))
        if self.archive and self.archive.uses_legacy_extent and self.offline.isChecked():
            self.info.setText("Acervo anterior: a suavização está disponível; para obter o novo recorte horizontal, desmarque offline e baixe/atualize a área uma vez.")
        if not self.scenes and self.offline.isChecked():
            self.info.setText("Não há cenas locais para esta área e período. Desmarque offline e baixe/atualize o acervo.")

    def import_scene(self):
        self.import_product(self.preset.currentData() if self.preset.currentData() in ("ndvi", "nbr") else "rgb")

    def import_ndvi(self):
        self.import_product("ndvi")

    def import_product(self, product):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.scenes): return
        self.active_scene = self.scenes[row]
        selected_rgb = tuple(combo.currentData() for combo in self.rgb_boxes)
        if product in ("ndvi", "nbr"):
            selected_rgb = index_keys(self.active_scene, product)
            if not selected_rgb:
                QMessageBox.warning(self, "Catálogo Multiespectral", "Esta cena não oferece NIR e vermelho para NDVI.")
                return
        property_layer = QgsProject.instance().mapLayer(self.layer_box.currentData())
        if property_layer is None:
            QMessageBox.warning(self, "Catálogo Multiespectral", "A camada do imóvel foi removida.")
            return
        crs = property_layer.crs()
        try:
            archive = LocalArchive(self.archive_path, self.area(), crs.authid() or crs.toWkt(),
                                   allow_legacy=self.offline.isChecked())
            if not self.archive or archive.area_id != self.archive.area_id or property_layer.id() != self.search_layer_id:
                raise CatalogError("O imóvel mudou desde a busca. Busque novamente antes de abrir a prévia.")
        except Exception as exc:
            QMessageBox.warning(self, "Catálogo Multiespectral", str(exc)); return
        self.active_archive = archive
        self.active_layer_id = property_layer.id()
        self.active_product = product
        self.active_bands = selected_rgb
        self.run_job("download", self.got_rasters, item=self.active_scene,
            archive=archive, rgb_keys=selected_rgb, product=product,
            offline=self.offline.isChecked(), force_download=self.repair.isChecked())

    def got_rasters(self, result):
        files, errors, composite = result
        acquired = (self.active_scene or {}).get("properties", {}).get("datetime", "")[:10]
        scene_id = (self.active_scene or {}).get("id", "cena")
        signature = "{}|{}|{}|{}".format(self.active_archive.area_id, scene_id,
                                          self.active_product, ",".join(self.active_bands))
        label = (self.active_product.upper() if self.active_product in ("ndvi", "nbr") else
                 "RGB {}".format("/".join(self.active_bands)))
        layer = QgsRasterLayer(composite, "{} | {} | {}".format(label, acquired, scene_id), "gdal")
        expected_bands = 1 if self.active_product in ("ndvi", "nbr") else 3
        if not layer.isValid() or layer.bandCount() != expected_bands:
            QMessageBox.warning(self, "Catálogo Multiespectral", "O QGIS não conseguiu abrir o raster {}.".format(label))
            return
        if self.active_product in ("ndvi", "nbr"):
            self.configure_ndvi(layer)
        else:
            self.configure_rgb(layer, self.smooth_rgb.isChecked())
        project = QgsProject.instance()
        property_layer = project.mapLayer(self.active_layer_id)
        if property_layer is None:
            QMessageBox.warning(self, "Prévia", "A camada do imóvel foi removida. Faça uma nova busca.")
            return
        props = self.active_scene.get("properties", {})
        description = "{} | {} | {} | Nuvens: {:.1f}% | {}".format(
            acquired, props.get("platform", ""), label, float(props.get("eo:cloud_cover", 0)), scene_id)
        if slc_gap_scene(self.active_scene):
            description += " | ATENÇÃO: lacunas reais do sensor Landsat 7 (SLC-off)"
        try:
            preview = PreviewDialog(layer, property_layer, description, self.iface,
                                    self.offline.isChecked(), self)
        except Exception as exc:
            QMessageBox.warning(self, "Prévia", "Não foi possível desenhar o limite: " + str(exc))
            return
        accepted = preview.exec() == QDialog.DialogCode.Accepted
        preview.deleteLater()
        for row, item in enumerate(self.scenes):
            self.table.setItem(row, 6, QTableWidgetItem(self.archive.status(item)))
        if not accepted:
            self.info.setText("Prévia fechada. A cena ficou no acervo; selecione outra para comparar.")
            return
        for existing in list(project.mapLayers().values()):
            if existing.customProperty("catalogo_multiespectral_assinatura", "") == signature:
                project.removeMapLayer(existing.id())
        layer.setCustomProperty("catalogo_multiespectral_assinatura", signature)
        layer.setCustomProperty("catalogo_multiespectral_cena", scene_id)
        layer.setCustomProperty("catalogo_multiespectral_data", acquired)
        layer.setCustomProperty("catalogo_multiespectral_bandas", ",".join(self.active_bands))
        project.addMapLayer(layer, False)
        root = project.layerTreeRoot()
        property_node = root.findLayer(self.active_layer_id)
        parent = property_node.parent() if property_node else root
        insertion = parent.children().index(property_node) + 1 if property_node else 0
        parent.insertLayer(insertion, layer)
        try:
            canvas = self.iface.mapCanvas()
            transform = QgsCoordinateTransform(layer.crs(), project.crs(), project)
            canvas.setExtent(transform.transformBoundingBox(layer.extent()))
            canvas.refresh()
        except Exception:
            self.iface.mapCanvas().refresh()
        self.info.setText("{} importado para {}. Arquivos preservados no acervo local.".format(label, acquired))

    @staticmethod
    def configure_ndvi(layer):
        colors = [(-1.0, "#312c51", "−1,00"),
                  (-0.2, "#8d6e99", "−0,20"),
                  (0.0, "#d7b8ac", "0,00"),
                  (0.2, "#e9dba0", "0,20"),
                  (0.4, "#afd26b", "0,40"),
                  (0.6, "#4d9d42", "0,60"),
                  (1.0, "#155b35", "1,00")]
        ramp = QgsColorRampShader(-1, 1)
        ramp.setColorRampType(QgsColorRampShader.Type.Interpolated)
        ramp.setColorRampItemList([QgsColorRampShader.ColorRampItem(value,
            QColor(color), label) for value, color, label in colors])
        shader = QgsRasterShader(-1, 1)
        shader.setRasterShaderFunction(ramp)
        layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
        layer.triggerRepaint()

    @staticmethod
    def configure_rgb(layer, smooth=True):
        provider = layer.dataProvider()
        renderer = QgsMultiBandColorRenderer(provider, 1, 2, 3)
        # Persist display limits; reopening the same composition avoids rescans.
        source = layer.source()
        stats_file = source + ".contraste.json"
        signature, limits = None, {}
        try:
            folder = os.path.dirname(source)
            signature = sorted((name, os.stat(os.path.join(folder, name)).st_mtime_ns,
                                os.stat(os.path.join(folder, name)).st_size)
                               for name in os.listdir(folder)
                               if name.endswith((".tif", ".vrt")))
            signature = [list(value) for value in signature]
            with open(stats_file, encoding="utf-8") as stream:
                cached = json.load(stream)
            if cached.get("signature") == signature:
                limits = cached.get("limits", {})
        except (OSError, ValueError, TypeError):
            limits = {}  # Missing/invalid cached display limits are recalculated.
        for band, setter in ((1, renderer.setRedContrastEnhancement),
                             (2, renderer.setGreenContrastEnhancement),
                             (3, renderer.setBlueContrastEnhancement)):
            try:
                if str(band) in limits:
                    low, high = limits[str(band)]
                else:
                    low, high = provider.cumulativeCut(band, 0.02, 0.98, layer.extent(), 262144)
                if high <= low:
                    stats = provider.bandStatistics(band)
                    low, high = stats.minimumValue, stats.maximumValue
                if math.isfinite(low) and math.isfinite(high) and high > low:
                    limits[str(band)] = [low, high]
                    enhancement = QgsContrastEnhancement(provider.dataType(band))
                    enhancement.setContrastEnhancementAlgorithm(
                        QgsContrastEnhancement.ContrastEnhancementAlgorithm.StretchToMinimumMaximum)
                    enhancement.setMinimumValue(low)
                    enhancement.setMaximumValue(high)
                    setter(enhancement)
            except Exception:
                logging.getLogger(__name__).warning("Não foi possível calcular o contraste da banda %s.", band)
        layer.setRenderer(renderer)
        resampling = layer.resampleFilter()
        if resampling:
            resampling.setZoomedInResampler(QgsCubicRasterResampler() if smooth else None)
            resampling.setZoomedOutResampler(QgsBilinearRasterResampler() if smooth else None)
            resampling.setMaxOversampling(2.0)
        layer.triggerRepaint()
        if signature is not None and len(limits) == 3:
            try:
                with open(stats_file + ".part", "w", encoding="utf-8") as stream:
                    json.dump({"signature": signature, "limits": limits}, stream, allow_nan=False)
                os.replace(stats_file + ".part", stats_file)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("Não foi possível salvar os limites de contraste.")

    def closeEvent(self, event):
        if self.job:
            self.cancel_job(); self.job.finished.connect(self.close); event.ignore()
        else:
            super().closeEvent(event)


class USGSCatalogPlugin:
    def __init__(self, iface):
        self.iface, self.action, self.dialog = iface, None, None

    def initGui(self):
        self.action = QAction(QIcon(os.path.join(os.path.dirname(__file__), "icon.png")),
                              "Catálogo Multiespectral por Área de Interesse", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dialog)
        self.iface.addPluginToRasterMenu("Catálogo Multiespectral", self.action)
        self.iface.addToolBarIcon(self.action)

    def show_dialog(self):
        if self.dialog is None:
            self.dialog = CatalogDialog(self.iface, self.iface.mainWindow())
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def unload(self):
        self.iface.removePluginRasterMenu("Catálogo Multiespectral", self.action)
        self.iface.removeToolBarIcon(self.action)
        if self.dialog:
            if self.dialog.job:
                self.dialog.job.cancel(); self.dialog.job.wait()
            self.dialog.close()
