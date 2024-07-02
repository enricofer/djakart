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
    elimina_pg_schema,
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
    elimina_pg_schema(ver)


class versioniTests(TestCase):

    databases = '__all__'
    maxDiff = None
    dsimport = "b0101_vincoli.gpkg"
    crs = "EPSG:3003"
    clone = None

    def setUp(self):
        self.testver = create_version(self.crs)
        if self.dsimport:
            gpkg_path = os.path.join(os.path.dirname(__file__),'test',self.dsimport)
            ext = self.testver.importa(gpkg_path)
    
    def tearDown(self):
        destroy_kart_version(self.testver)
        if self.clone:
            destroy_kart_version(self.clone)


    #def envver(crs="EPSG:32632", dsimport=None):
    #    def decorator(func):
    #        def wrapper(version_test_case):
    #            new_ver = create_version(crs)
    #            if dsimport:
    #                gpkg_path = os.path.join(os.path.dirname(__file__),'test',dsimport)
    #                ext = new_ver.importa(gpkg_path)
    #            func(version_test_case,new_ver)
    #            new_ver.delete()
    #            destroy_kart_version(new_ver)
    #        wrapper.__name__ = func.__name__
    #        return wrapper
    #    return decorator

    #@envver(crs="EPSG:32632")
    def test_create_newversion(self):
        self.assertFalse(not self.testver.pk, "Version %s" % self.testver.nome)

    #@envver(crs="EPSG:32632", dsimport='test_data_state_A.gpkg')
    def test_import_dataset(self):
        tabs = self.testver.kart_tables
        self.assertTrue((tabs[0] == 'b0101011_Vincolo' and tabs[1] == 'b0101021_VincoloPaesaggist' and tabs[2] == 'b0101031_VincDestForestale'), "Version %s" % self.testver.nome)

    def test_clone(self):
        self.clone = version.objects.create(
            nome=uuid.uuid4().hex[0:4], 
            crs=self.testver.crs,
            base=self.testver
        )
        tabs = self.clone.kart_tables
        self.assertTrue((tabs[0] == 'b0101011_Vincolo' and tabs[1] == 'b0101021_VincoloPaesaggist' and tabs[2] == 'b0101031_VincDestForestale'), "Cloned version %s" % self.clone.nome)


    def test_insert(self):
        connection = get_pg_versions_connection()
        cursor = connection.cursor()
        self.clone = version.objects.create(
            nome=uuid.uuid4().hex[0:4], 
            crs=self.testver.crs,
            base=self.testver
        )

        sql_add = """
INSERT INTO "{schema}"."b0101011_Vincolo"(fid, "ARTICOLO", "DETTVINC", geom) VALUES (nextval('"{schema}"."b0101011_Vincolo_fid_seq"'::regclass), '{schema}', 99, 'MultiPolygon (((1722916.68287772010080516 5034227.90152797847986221, 1724565.71380323800258338 5035908.84918108768761158, 1725235.96508264215663075 5033802.34516010340303183, 1722916.68287772010080516 5034227.90152797847986221)))'); 
""".format(schema=self.clone.schema)
        print (sql_add)
        cursor.execute(sql_add)
        print ("cursor.statusmessage",cursor.statusmessage)
        connection.commit()
        self.clone.salva_cache()
        self.assertTrue(self.clone.cambiamenti_non_registrati, "Cloned version %s" % self.clone.nome)


    def test_update(self):
        connection = get_pg_versions_connection()

        cursor = connection.cursor()
        self.clone = version.objects.create(
            nome=uuid.uuid4().hex[0:4], 
            crs=self.testver.crs,
            base=self.testver
        )

        sql_updt = """
UPDATE "{schema}"."b0101011_Vincolo"
SET "ARTICOLO" = 'TEST' WHERE "N_AREAV"='0015';
""".format(schema=self.clone.schema)
        cursor.execute(sql_updt)
        connection.commit()
        self.clone.salva_cache()
        self.assertTrue(self.clone.cambiamenti_non_registrati, "Cloned version %s" % self.clone.nome)
