from django.test import TestCase,override_settings
from django.template import Template, Context
from django.conf import settings

import psycopg2

import hashlib
import json
import uuid
import os

from djakart.kart_api import (
    KartException,
    get_pg_versions_connection,
    crea_nuova_versione,
    elimina_versione, 
    crea_nuovo_repository,
    log_versione,
    merge_versione, 
    status_versione, 
    grant_select_schema, 
    resolve_conflitto,
    conflitti_versione,  
    undo_commit_versione,
    show_versione,
    restore_versione,
    commit_versione,
    pull_versione,
    merged_list_versione,
    kart_cmd,
    importa_dataset,
    aggiorna_riferimenti,
    config_user_versione,
    list_versioned_tables,
    geo_tables,
    KART_PGUSER,
    KART_PGUSER_PWD
) 

from djakart.models import (
    version
)

def get_pg_uri(schema):
    return '''PG:"dbname='{dbname}' host='{host}' port='{port}' user='{user}' password='{pwd}' active_schema='{schema}'"'''.format(
            dbname=settings.DBPREFIX + os.environ.get("VERSION_DB", ""),
            host=os.environ.get("HOST_EXTERNAL", ""),
            port=os.environ.get("POSTGRES_PORT_EXTERNAL", ""),
            user=os.environ.get("POSTGRES_USER", ""),
            pwd=os.environ.get("POSTGRES_PASSWORD", ""),
            schema=schema
        )

def create_version(crs):
    newver = version()
    newver.nome = uuid.uuid4().hex[0:4]
    newver.crs = crs
    newver.save()
    return newver

def destroy_kart_version(ver):
    version_path = os.path.join(settings.KART_REPO, ver.nome)
    os.system('rm -Rf %s' % version_path)
    os.system('rm -f %s*.*' % version_path)

#@override_settings(DBPREFIX="test_")
class versioniTests(TestCase):

    databases = '__all__'
    maxDiff = None

    def envver(crs="EPSG:32632", dsimport=None):
        def decorator(func):
            def wrapper(version_test_case):
                new_ver = create_version(crs)
                if dsimport:
                    gpkg_path = os.path.join(os.path.dirname(__file__),'test',dsimport)
                    ext = new_ver.importa(gpkg_path)
                func(version_test_case,new_ver)
                new_ver.delete()
                destroy_kart_version(new_ver)
            wrapper.__name__ = func.__name__
            return wrapper
        return decorator

    @envver(crs="EPSG:32632")
    def test_create_newversion(self,testver):
        print ("DATABASES",self.databases)
        self.assertFalse(not testver.pk, "Version %s" % testver.nome)

    @envver(crs="EPSG:32632", dsimport='test_data_state_A.gpkg')
    def test_import_dataset(self,testver):
        tabs = testver.kart_tables
        self.assertTrue((tabs[0] == '01_one' and tabs[1] == 'basetiles'), "Version %s" % testver.nome)

    @envver(crs="EPSG:32632", dsimport='test_data_state_A.gpkg')
    def test_clone(self,testver):
        clone = version.objects.create(
            nome=uuid.uuid4().hex[0:4], 
            crs=testver.crs,
            base=testver
        )
        tabs = clone.kart_tables
        print ("clone tabs", tabs)
        self.assertTrue((tabs[0] == '01_one' and tabs[1] == 'basetiles'), "Cloned version %s" % clone.nome)

    @envver(crs="EPSG:32632", dsimport='test_data_state_A.gpkg')
    def test_insert_and_commit(self,testver):
        cursor = get_pg_versions_connection().cursor()
        clone = version.objects.create(
            nome=uuid.uuid4().hex[0:4], 
            crs=testver.crs,
            base=testver
        )

        cursor.execute("SELECT schema_name FROM information_schema.schemata")
        res = cursor.fetchall()
        print ("SCHEMAS", res) #
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = '%s'" % testver.schema)
        res = cursor.fetchall()
        print ("SCHEMA", testver.schema, "TABLES", res) 
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = '%s'" % clone.schema)
        res = cursor.fetchall()
        print ("SCHEMA", clone.schema, "TABLES", res) 


        sql_add = """
INSERT INTO "{schema}"."basetiles"(fid, layer, content, geom) VALUES (nextval('"{schema}"."basetiles_fid_seq"'::regclass), '{schema}', 1, 'MultiPolygon Z (((725034.29041177907492965 5036778.0809512697160244 0, 726719.34362095000687987 5036778.0809512697160244 0, 725896.41065833170432597 5035210.58959390129894018 0, 725034.29041177907492965 5036778.0809512697160244 0)))'); 
""".format(schema=clone.schema)
        print("cursor", cursor.execute(sql_add))
        print("SQL", sql_add)
        #ogr_cmd = '''ogrinfo -ro {conn} -sql "{sql}"'''.format(conn=get_pg_uri(clone.schema), sql=sql_add)
        #print (ogr_cmd)
        #os.system(ogr_cmd)
        print ("STAtUS", clone.status, "cambiamenti_non_registrati", clone.cambiamenti_non_registrati)
        self.assertTrue(clone.cambiamenti_non_registrati, "Cloned version %s" % clone.nome)

    @envver(crs="EPSG:32632", dsimport='test_data_state_A.gpkg')
    def test_update_and_commit(self,testver):
        print ("kart.workingcopy.location", testver.get_config('kart.workingcopy.location'))
        cursor = get_pg_versions_connection().cursor()
        clone = version.objects.create(
            nome=uuid.uuid4().hex[0:4], 
            crs=testver.crs,
            base=testver
        )

        sql_select = """
SELECT layer,content FROM "{schema}"."basetiles"
""".format(schema=clone.schema)
        res = cursor.execute(sql_select)
        rows = cursor.fetchall()
        print(1,sql_select, res, rows)

        sql_add = """
UPDATE "{schema}"."basetiles"
SET content = 9999 WHERE layer='tile4'
""".format(schema=clone.schema)
        print("cursor", cursor.execute(sql_add))
        print("SQL", sql_add)
        #ogr_cmd = '''ogrinfo -ro {conn} -sql "{sql}"'''.format(conn=get_pg_uri(clone.schema), sql=sql_add)
        #print (ogr_cmd)
        #os.system(ogr_cmd)
        res = cursor.execute(sql_select)
        rows = cursor.fetchall()
        print ("kart.workingcopy.location", clone.get_config('kart.workingcopy.location'))
        print(2,sql_select, res, rows)
        print ("STAtUS", clone.status_(), "cambiamenti_non_registrati", clone.cambiamenti_non_registrati, clone.is_clean_())
        self.assertTrue(clone.cambiamenti_non_registrati, "Cloned version %s" % clone.nome)

    @staticmethod
    def disconnect(self,*args, **kwargs):
        print("disconnect", args,kwargs)