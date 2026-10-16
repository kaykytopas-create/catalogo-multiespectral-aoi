# SPDX-License-Identifier: GPL-2.0-or-later
"""Anonymous Landsat federation: Planetary Computer and INPE BDC scenes only."""
import copy,json,urllib.parse
from .stac import PublicCatalog,CatalogError,visible_scenes,search_payload
INPE_ROOT='https://data.inpe.br/bdc/stac/v1/'
INPE_COLLECTION='landsat-2'

class SearchResults(list):
    def __init__(self,items=(),warnings=()):super().__init__(items);self.warnings=list(warnings)


def inpe_url(url):
    p=urllib.parse.urlparse(url)
    try:return p.scheme=='https' and p.hostname=='data.inpe.br' and p.port in (None,443) and not p.username and not p.password and p.path.startswith('/bdc/stac/v1/')
    except ValueError:return False


def normalize_inpe(item):
    if item.get('collection')!=INPE_COLLECTION:raise CatalogError('Coleção INPE inesperada; mosaicos e cubos temporais não são cenas individuais.')
    item=copy.deepcopy(item);item['catalog:original_collection']=INPE_COLLECTION;item['collection']='landsat-c2-l2'
    item['catalog:sources']=['INPE/Brazil Data Cube']
    prefix=item.get('id','')[:4];satellite={'LT04':'landsat-4','LT05':'landsat-5','LE07':'landsat-7','LC08':'landsat-8','LC09':'landsat-9'}.get(prefix)
    if not satellite:raise CatalogError('Sensor Landsat não reconhecido no INPE.')
    item.setdefault('properties',{})['platform']=satellite
    for key,asset in item.get('assets',{}).items():
        if key in ('blue','green','red','nir08','swir16','swir22','coastal'):
            asset['eo:bands']=[{'name':key,'common_name':key}]
            asset['raster:bands']=[{'scale':.0000275,'offset':-.2,'nodata':0}]
    return item


def merge_scenes(items):
    unique={}
    for raw in items:
        key=(raw.get('collection'),raw.get('id'))
        if key not in unique:unique[key]=copy.deepcopy(raw);continue
        item=unique[key]
        item['catalog:sources']=list(dict.fromkeys(item.get('catalog:sources',[])+raw.get('catalog:sources',[])))
        if raw.get('catalog:download_sources'):
            item.setdefault('catalog:download_sources',{}).update(raw['catalog:download_sources'])
        for name,asset in raw.get('assets',{}).items():
            if name not in item.setdefault('assets',{}):item['assets'][name]=copy.deepcopy(asset);continue
            existing=item['assets'][name]
            alternatives=existing.get('catalog:alternate_hrefs',[])+[asset.get('href')]+asset.get('catalog:alternate_hrefs',[])
            existing['catalog:alternate_hrefs']=list(dict.fromkeys(h for h in alternatives if h and h!=existing.get('href')))
    return list(unique.values())


class MultiCatalog(PublicCatalog):
    def search_inpe(self,rect,start,end,next_link=None):
        if next_link:
            url=next_link.get('href','')
            if not inpe_url(url) or next_link.get('method','GET').upper()!='GET':raise CatalogError('Paginação INPE inválida.')
        else:
            # This INPE endpoint currently returns HTTP 500 for STAC query.
            # Traverse unfiltered pages, applying the same strict cloud gate locally.
            params={'collections':INPE_COLLECTION,'bbox':','.join(map(str,rect)),
                    'datetime':start+'T00:00:00Z/'+end+'T23:59:59Z','limit':100}
            url=INPE_ROOT+'search?'+urllib.parse.urlencode(params)
        data=self.json_request(url)
        if data.get('type')!='FeatureCollection':raise CatalogError('Resposta INPE sem lista de cenas.')
        result=[normalize_inpe(item) for item in data.get('features',[])]
        link=next((l for l in data.get('links',[]) if l.get('rel')=='next'),None)
        return visible_scenes(result),link

    def search(self,collections,rect,start,end,next_link=None):
        search_payload(collections,rect,start,end)  # validate parameters first
        initial=next_link is None
        if not initial and next_link.get('catalog:federated')!=1:raise CatalogError('Paginação combinada inválida; refaça a pesquisa.')
        state={} if initial else next_link
        warnings=list(state.get('warnings',[]));items=[];following={};success=0
        for source in ('pc','inpe'):
            if source=='inpe' and 'landsat-c2-l2' not in collections:continue
            if not initial and source not in state.get('streams',{}):continue
            link=None if initial else state['streams'][source]
            if self.cancelled():raise CatalogError('Operação cancelada.')
            try:
                page,nxt=super().search(collections,rect,start,end,link) if source=='pc' else self.search_inpe(rect,start,end,link)
                if source=='pc':
                    for item in page:item.setdefault('catalog:sources',['Microsoft Planetary Computer'])
                items.extend(page);success+=1
                if nxt:following[source]=nxt
            except Exception as exc:
                if self.cancelled():raise CatalogError('Operação cancelada.') from exc
                warnings.append(('Microsoft Planetary Computer' if source=='pc' else 'INPE/Brazil Data Cube')+': consulta incompleta — '+str(exc))
        if not success:raise CatalogError('Nenhuma fonte respondeu nesta etapa. '+ '; '.join(warnings))
        token={'catalog:federated':1,'streams':following,'warnings':warnings} if following else None
        return SearchResults(merge_scenes(items),warnings),token
