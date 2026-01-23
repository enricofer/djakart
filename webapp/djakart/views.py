from django.shortcuts import render
from django.template.loader import render_to_string
from django.template import Context, Template
from django.http import HttpResponseRedirect,JsonResponse,HttpResponse,FileResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView

from .models import version, writeQgs,basemap

from .kart_api import (
    executeCmd,
    log_versione,
    status_versione, 
    show_versione,
    _diff_view,
    commit_versione,
    version_details,
    genera_diff_versione,
    restore_versione,
    list_versioned_tables,
    geo_tables,
    aggiorna_cache_versione,
    KART_PGUSER,
    KART_PGUSER_PWD

) 

import uuid
import requests
import json
import re
import os
import io
import psycopg2
from xml.sax.saxutils import escape
from urllib.parse import quote,unquote,parse_qs

VERSIONI_USER_GROUP = "gis"
SRID = os.environ.get("REPO_CRS")
SRID_CODE = SRID.split(":")[1]

def is_member(user):
    return user.groups.filter(name=VERSIONI_USER_GROUP).exists()

# Create your views here.

def log(request,versione):
    obj = version.objects.get(nome=versione)
    jlog = log_versione(obj.nome,jsonoutput=True )
    print (type(jlog))
    return JsonResponse(jlog, safe=False)

def show(request,versione):
    obj = version.objects.get(nome=versione)
    jshow = show_versione(obj.nome,jsonoutput=True )
    return JsonResponse(jshow, safe=False)

def status(request,versione):
    obj = version.objects.get(nome=versione)
    status = status_versione(obj.nome)
    return render(request, 'log.html', {'log': status})

def diff(request,versione,hash,parent_hash=""):
    formato = request.GET.get('format')
    versione_obj = version.objects.get(nome=versione)
    diff = genera_diff_versione(versione,hash,parent_hash,crs=versione_obj.crs, extent=versione_obj.extent, format=formato)
    print (diff)
    return HttpResponse(diff)

def diff_view(request,versione):
    versione_obj = version.objects.get(nome=versione)
    response =  HttpResponse(_diff_view(versione_obj.crs, versione_obj.extent))
    response['Content-Disposition'] = 'inline; filename="diff-view.html"'
    return response

def vlayer(request,versione,hash_from,hash_to, write_file=False):
    geojson_obj = version_details(versione, hash_from, hash_to)
    if write_file:
        vlayer_path = os.path.join("/kart_versions", versione+'.geojson')
        with open(vlayer_path, 'w') as f:
            f.write(json.dumps(geojson_obj))
    return JsonResponse(geojson_obj, safe=False)

def QGS_progetto(request,versione):
    versione_obj = version.objects.get(nome=versione)
    progetto = writeQgs(versione_obj)
    response = HttpResponse(progetto, content_type='application/xml')
    response['Content-Disposition'] = 'attachment; filename="%s.qgs"' % versione
    return response

def geojson_summary(request,versione):
    versione_obj = version.objects.get(nome=versione)
    summary = versione_obj.sommario_versione()
    response = HttpResponse(summary, content_type='application/geo+json')
    response['Content-Disposition'] = 'attachment; filename="%s.geojson"' % versione
    return response

def basemaps_js(request,depth):
    lyrsdef = basemap.getLyrs(depth)
    return HttpResponse(lyrsdef, content_type="text/javascript; charset=utf-8")


def summary(versione_id):
    versione_obj = version.objects.get(pk=versione_id)
    summary_path = os.path.join("/kart_versions", versione_obj.nome+'.geojson')
    if os.path.exists(summary_path):
        print ("summary_path", summary_path)
        with open(summary_path, 'r') as f:
            geojson_obj = json.load(f)
            geojson_js = "JSON.parse('"+json.dumps(geojson_obj)+"')"
    else:
        #geojson_obj = versione_obj.sommario_versione()
        geojson_js = 'undefined /* error: summary not available */'
    return geojson_js

def params_js(request,versione_id):
    versione_obj = version.objects.get(pk=versione_id)
    paramsdef = 'var params = {'
    paramsdef += 'version: "{}", '.format(versione_obj.nome) 
    paramsdef += 'base: "{}", '.format(versione_obj.base.nome if versione_obj.base else versione_obj.nome) 
    paramsdef += 'archiviato: {}, '.format("true" if versione_obj.archiviato else "false")
    paramsdef += 'site_subpath: "{}", '.format(settings.SITE_SUBPATH)
    paramsdef += 'crs: "{}", '.format(versione_obj.crs)
    paramsdef += 'polyJSON: ' + summary(versione_id)
    paramsdef += '}'
    return HttpResponse(paramsdef, content_type="text/javascript; charset=utf-8")

@login_required
#@csrf_exempt
def kart_api(request,cmdstring):
    print("USER", request.user)
    if cmdstring.endswith("/"):
        cmdstring = cmdstring[:-1]
    cmds = cmdstring.split("/")
    repo = cmds[0]
    repo_path = os.path.join(settings.KART_REPO,repo)
    args = ["--repo", repo_path ] + cmds[1:]
    clean_args = [a.replace("|","/") for a in args]
    res = executeCmd(clean_args) #,jsonoutput=True
    try:
        jsres = json.loads(res)
        return JsonResponse(jsres)
    except:
        return HttpResponse(res, content_type='text/plain')

@login_required
#@csrf_exempt
def update(request,version_id):
    try:
        aggiorna_cache_versione(version_id)
        res = "OK"
    except Exception as E:
        res = "KO: %s" % str(E)
    return JsonResponse({"result": res})

#@login_required
@csrf_exempt
def set_version_extent(request, version_id):
    print ("version_id", version_id)
    res = "fail"
    versione_obj = version.objects.get(pk=version_id)
    if request.method == 'POST':
        extent = json.loads(request.body)["extent"]
        print ("extent",extent)
        versione_obj.extent = extent
        versione_obj.save()
        res = "ok"
    return JsonResponse({"result": res})

def vlist(request,versione_id):
    obj = version.objects.get(pk=versione_id)
    if obj.pk:
        evid = ""
        base_service = obj.base.mapping_service_url if obj.base else ""

        all_versions = [{
            "nome": "Versione corrente: " + obj.nome,
            "wms": obj.mapping_service_url,
        }]

        if obj.base:
            all_versions.append({
                "nome": "Base corrente: " + obj.base.nome,
                "wms": obj.base.mapping_service_url,
            })
            if obj.base != obj.origine:
                all_versions.append({
                    "nome": "Base origine: " + obj.origine.nome,
                    "wms": obj.origine.mapping_service_url,
                })
        else:
            all_versions.append({
                "nome": "",
                "wms": ""
            })

        for v in version.objects.all():
            if v.pk == obj.pk or (obj.base and v.pk == obj.base.pk) or (obj.origine and v.pk == obj.origine.pk):
                continue

            all_versions.append({
                "nome": v.nome,
                "wms": v.mapping_service_url,
            })
    else:
        all_versions = {}

    response = render(
        request, 
        'tutte_le_versioni.js',
        {'current_version': obj, 'vlist': json.dumps(all_versions)},
        content_type="text/javascript"
    )

    #response['Content-Disposition'] = 'attachment; filename="tutte_le_versioni.js"'

    return response

class mvt_view(ListView):
#portion of code from https://github.com/pramsey/minimal-mvt

    # Table to query for MVT data, and columns to
# include in the tiles.
    TABLE = {
        'table':       'dbt_export',
        'srid':        '3003',
        'geomColumn':  'geom',
        'attrColumns': None
    }  

    DATABASE_CONNECTION = None

    def get_pg_versions_connection(self):
        connection = psycopg2.connect(
            database=os.environ.get("VERSION_DB", "blabla"),
            user=os.environ.get("POSTGRES_USER", "blabla"),
            password=os.environ.get("POSTGRES_PASSWORD", "blabla"),
            host=os.environ.get("POSTGRES_SERVER", "blabla"),
            port=os.environ.get("POSTGRES_PORT", "blabla")
        )
        return connection

    # Do we have all keys we need? 
    # Do the tile x/y coordinates make sense at this zoom level?
    def tileIsValid(self):
        if not (self.x and self.y and self.zoom):
            return False
        if self.format not in ['pbf', 'mvt']:
            return False
        size = 2 ** self.zoom;
        if self.x >= size or self.y >= size:
            return False
        if self.x < 0 or self.y < 0:
            return False
        return True


    # Calculate envelope in "Spherical Mercator" (https://epsg.io/3857)
    def tileToEnvelope(self):
        # Width of world in EPSG:3857
        worldMercMax = 20037508.3427892
        worldMercMin = -1 * worldMercMax
        worldMercSize = worldMercMax - worldMercMin
        # Width in tiles
        worldTileSize = 2 ** self.zoom
        # Tile width in EPSG:3857
        tileMercSize = worldMercSize / worldTileSize
        # Calculate geographic bounds from tile coordinates
        # XYZ tile coordinates are in "image space" so origin is
        # top-left, not bottom right
        env = dict()
        env['xmin'] = worldMercMin + tileMercSize * self.x
        env['xmax'] = worldMercMin + tileMercSize * (self.x + 1)
        env['ymin'] = worldMercMax - tileMercSize * (self.y + 1)
        env['ymax'] = worldMercMax - tileMercSize * (self.y)
        return env


    # Generate SQL to materialize a query envelope in EPSG:3857.
    # Densify the edges a little so the envelope can be
    # safely converted to other coordinate systems.
    def envelopeToBoundsSQL(self, env):
        DENSIFY_FACTOR = 4
        env['segSize'] = (env['xmax'] - env['xmin'])/DENSIFY_FACTOR
        sql_tmpl = 'ST_Segmentize(ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, 3857),{segSize})'
        return sql_tmpl.format(**env)


    # Generate a SQL query to pull a tile worth of MVT data
    # from the table of interest.        
    def envelopeToSQL(self, env):
        tbl = self.TABLE.copy()
        tbl["repo"] = self.repo
        tbl["table"] = self.layer
        tbl['env'] = self.envelopeToBoundsSQL(env)
        if not tbl['attrColumns']:
            tbl['attrColumns'] = self.getAttrs()
        # Materialize the bounds
        # Select the relevant geometry and clip to MVT bounds
        # Convert to MVT format
        sql_tmpl = """
            WITH 
            bounds AS (
                SELECT {env} AS geom, 
                       {env}::box2d AS b2d
            ),
            mvtgeom AS (
                SELECT ST_AsMVTGeom(ST_Transform(t.{geomColumn}, 3857), bounds.b2d) AS geom, 
                       {attrColumns}
                FROM "{repo}"."{table}" t, bounds
                WHERE ST_Intersects(t.{geomColumn}, ST_Transform(bounds.geom, {srid}))
            ) 
            SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
        """
        return sql_tmpl.format(**tbl)


    # Run tile query SQL and return error on failure conditions
    def sqlToPbf(self, sql):

        # Query for MVT
        with self.DATABASE_CONNECTION.cursor() as cur:
            cur.execute(sql)
            if not cur:
                self.send_error(404, "sql query failed: %s" % (sql))
                return None
            return cur.fetchone()[0]
        
        return None
    
    def getAttrs(self):
        with self.DATABASE_CONNECTION.cursor() as cur:
            cur.execute("""
select array_to_string(array(select '"' || column_name || '"' from information_schema.columns 
where table_schema = '{repo}' and table_name = '{layer}' and column_name != '{geomfield}'),',')""".format(
                repo=self.repo,
                layer=self.layer,
                geomfield = self.TABLE["geomColumn"]
            ))
            return cur.fetchone()[0]

    def build_connection(self):
        # Make and hold connection to database
        if not self.DATABASE_CONNECTION:
            try:
                self.DATABASE_CONNECTION = self.get_pg_versions_connection()
            except (Exception, psycopg2.Error) as error:
                self.send_error(500, "cannot connect to dbt" )
                return None

    def get(self,request,repo=None,layer=None,zoom=None,x=None,y=None,format=None):

        self.build_connection()
        self.repo = repo
        self.layer = layer

        print ("atrrs", self.getAttrs())

        self.zoom = int(zoom)
        self.x = int(x)
        self.y = int(y)
        self.format = format

        if not (self.tileIsValid()):
            self.send_error(400, "invalid tile path ZXY: %d/%d/%d" % (self.zoom, self.x, self.y))
            return

        env = self.tileToEnvelope()
        sql = self.envelopeToSQL(env)
        pbf = self.sqlToPbf(sql)

        print ("MVT request: %d/%d/%d\n env: %s" % (self.zoom, self.x, self.y, env))

        b = io.BytesIO(pbf)

        return FileResponse(b)
