# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Persistent per-AOI archive. No QGIS imports; safe for background workers."""
import hashlib
import json
import os
from datetime import datetime, timezone

from .stac import CROP_PROFILE, CatalogError, available_bands, raster_assets, visible_scenes


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()[:24]


class LocalArchive:
    def __init__(self, root, rect, target_crs, allow_legacy=False):
        self.rect = tuple(float(value) for value in rect)
        self.target_crs = target_crs
        # The crop and its CRS are part of the identity: never reuse another AOI.
        self.area_id = digest({"bbox": [round(v, 8) for v in self.rect],
                               "crs": target_crs, "context": CROP_PROFILE})
        self.folder = os.path.join(os.path.abspath(root), "areas", self.area_id)
        self.index_path = os.path.join(self.folder, "catalogo.json")
        self.uses_legacy_extent = False
        if allow_legacy and not os.path.isfile(self.index_path):
            legacy_id = digest({"bbox": [round(v, 8) for v in self.rect],
                                "crs": target_crs, "context": [3.2, 2.4]})
            legacy_folder = os.path.join(os.path.abspath(root), "areas", legacy_id)
            if os.path.isfile(os.path.join(legacy_folder, "catalogo.json")):
                self.area_id, self.folder = legacy_id, legacy_folder
                self.index_path = os.path.join(self.folder, "catalogo.json")
                self.uses_legacy_extent = True

    def read(self):
        if not os.path.isfile(self.index_path):
            return {"version": 1, "bbox": self.rect, "crs": self.target_crs, "scenes": {}}
        try:
            with open(self.index_path, encoding="utf-8") as stream:
                index = json.load(stream)
            if index.get("version") != 1 or not isinstance(index.get("scenes"), dict):
                raise ValueError("formato desconhecido")
            return index
        except (OSError, ValueError) as exc:
            raise CatalogError("Não foi possível ler o catálogo local: " + str(exc)) from exc

    def write(self, index):
        os.makedirs(self.folder, exist_ok=True)
        partial = self.index_path + ".part"
        with open(partial, "w", encoding="utf-8") as stream:
            json.dump(index, stream, ensure_ascii=False, indent=2)
        os.replace(partial, self.index_path)

    @staticmethod
    def scene_key(item):
        return digest([item.get("collection"), item.get("id")])

    def scene_folder(self, item):
        return os.path.join(self.folder, "cenas", self.scene_key(item))

    def remember(self, item, errors=None):
        index = self.read()
        index["scenes"][self.scene_key(item)] = {
            "item": item, "updated": datetime.now(timezone.utc).isoformat(),
            "errors": list(errors or [])}
        self.write(index)

    def remember_many(self, items):
        index = self.read()
        for item in items:
            key = self.scene_key(item)
            previous = index["scenes"].get(key, {})
            index["scenes"][key] = {**previous, "item": item}
        self.write(index)

    def cached_keys(self, item):
        folder = self.scene_folder(item)
        # Only finished files count. .part.tif files are never reusable.
        from .stac import PublicCatalog
        return {key for key, href in raster_assets(item)
                if os.path.isfile(PublicCatalog.cached_band_path(item, folder, key, href))
                and os.path.getsize(PublicCatalog.cached_band_path(item, folder, key, href)) > 0}

    def status(self, item):
        keys = {key for key, _ in available_bands(item)}
        cached = self.cached_keys(item)
        if keys and keys.issubset(cached):
            return "Completo"
        return "Parcial ({}/{})".format(len(cached), len(keys)) if cached else "Não baixado"

    def search(self, collections, start, end):
        result = []
        for record in self.read()["scenes"].values():
            item = record["item"]
            acquired = str(item.get("properties", {}).get("datetime", ""))[:10]
            if item.get("collection") in collections and start <= acquired <= end:
                result.append(item)
        result = visible_scenes(result)
        result.sort(key=lambda item: item.get("properties", {}).get("datetime", ""), reverse=True)
        return result

    def sync(self, client, collections, start, end, progress):
        """Re-query every page, downloading only missing spectral bands."""
        items, seen, visited_links, link = [], set(), set(), None
        while True:
            if client.cancelled():
                raise CatalogError("Operação cancelada; bandas já concluídas foram mantidas.")
            progress("Consultando todas as páginas do período… {} cenas".format(len(items)))
            page, next_link = client.search(collections, self.rect, start, end, link)
            for item in page:
                key = self.scene_key(item)
                if key not in seen:
                    seen.add(key)
                    items.append(item)
            if not next_link:
                break
            signature = digest(next_link)
            if signature in visited_links:
                raise CatalogError("O catálogo repetiu a paginação; tente atualizar novamente.")
            visited_links.add(signature)
            link = next_link
        completed, failed = 0, []
        for number, item in enumerate(items, 1):
            if client.cancelled():
                raise CatalogError("Operação cancelada; bandas já concluídas foram mantidas.")
            prefix = "Cena {}/{} | {} | ".format(number, len(items), item.get("id", ""))
            self.remember(item)
            try:
                keys = [key for key, _ in available_bands(item)]
                _, errors = client.cache_bands(item, self.scene_folder(item), self.rect,
                    self.target_crs, lambda message: progress(prefix + message), keys)
                self.remember(item, errors)
                if errors:
                    failed.append("{}: {}".format(item.get("id"), "; ".join(errors)))
                else:
                    completed += 1
            except Exception as exc:
                if client.cancelled():
                    raise CatalogError("Operação cancelada; bandas já concluídas foram mantidas.") from exc
                self.remember(item, [str(exc)])
                failed.append("{}: {}".format(item.get("id"), exc))
        index = self.read()
        index["last_sync"] = datetime.now(timezone.utc).isoformat()
        self.write(index)
        return {"items": items, "completed": completed, "errors": failed}
